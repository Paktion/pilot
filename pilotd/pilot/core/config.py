"""
Persistent JSON configuration at ``$PILOT_HOME/config.json``.

Schema-validated with type checking. ``PILOT_<UPPER_KEY>`` env overrides.
Atomic writes via tmp+rename.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from pilot.core import paths

log = logging.getLogger("pilotd.config")

_ANY = "any"
_SENTINEL = object()


class Config:
    """Manages persistent Pilot configuration."""

    CONFIG_SCHEMA: dict[str, tuple[type | tuple[type, ...] | str, Any]] = {
        "model":                  (str,                "claude-sonnet-4-20250514"),
        "model_light":            (str,                "claude-haiku-4-5-20251001"),
        "max_steps":              (int,                50),
        "verbose":                (bool,               True),
        "save_screenshots":       (bool,               True),
        "confirm_destructive":    (bool,               True),
        "blocked_apps":           (list,               []),
        "max_actions_per_minute": (int,                20),
        "retina_scale":           ((int, float),       2.0),
        "action_delay":           ((int, float),       0.3),
        "safety_enabled":         (bool,               True),
        "max_daily_budget":       ((int, float),       5.0),
        "max_monthly_budget":     ((int, float),       50.0),
        "per_task_budget":        ((int, float),       1.0),
        "log_level":              (str,                "INFO"),
        "session_retention_days": (int,                30),
        "use_cgevent":            (bool,               True),
    }

    DEFAULT_CONFIG: dict[str, Any] = {k: v for k, (_t, v) in CONFIG_SCHEMA.items()}

    def __init__(self, config_path: str | Path | None = None) -> None:
        self._path = Path(config_path).expanduser() if config_path else paths.config_path()
        self._data: dict[str, Any] = {}
        self._load()

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._validate(key, value)
        self._data[key] = value
        self._save()

    def reset(self) -> None:
        self._data = dict(self.DEFAULT_CONFIG)
        self._save()

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data)

    @classmethod
    def _validate(cls, key: str, value: Any) -> None:
        if key not in cls.CONFIG_SCHEMA:
            known = ", ".join(sorted(cls.CONFIG_SCHEMA))
            raise KeyError(f"Unknown config key {key!r}. Valid keys: {known}")
        expected_type, _default = cls.CONFIG_SCHEMA[key]
        if value is None or expected_type == _ANY:
            return
        if not isinstance(value, expected_type):
            type_name = (
                expected_type.__name__
                if isinstance(expected_type, type)
                else " or ".join(t.__name__ for t in expected_type)
            )
            raise TypeError(
                f"Config key {key!r} expects {type_name}, got {type(value).__name__}"
            )

    def apply_env_overrides(self) -> None:
        """``PILOT_<UPPER_KEY>`` env vars override stored values.

        PILOT_PROMPT_* is reserved for prompts and never maps to a config key.
        """
        prefix = "PILOT_"
        for env_key, env_value in os.environ.items():
            if not env_key.startswith(prefix):
                continue
            if env_key.startswith("PILOT_PROMPT_"):
                continue
            config_key = env_key[len(prefix):].lower()
            if config_key not in self.CONFIG_SCHEMA:
                continue
            coerced = self._coerce_env_value(config_key, env_value)
            if coerced is not _SENTINEL:
                self._data[config_key] = coerced

    @classmethod
    def _coerce_env_value(cls, key: str, raw: str) -> Any:
        expected_type, _ = cls.CONFIG_SCHEMA[key]
        if expected_type == _ANY or expected_type is str:
            return raw
        if expected_type is bool or (
            isinstance(expected_type, tuple) and bool in expected_type
        ):
            return raw.lower() in ("1", "true", "yes", "on")
        if expected_type is int:
            try:
                return int(raw)
            except ValueError:
                log.warning("Cannot coerce env %s=%r to int", key, raw)
                return _SENTINEL
        if expected_type is float or (
            isinstance(expected_type, tuple) and float in expected_type
        ):
            try:
                return float(raw)
            except ValueError:
                log.warning("Cannot coerce env %s=%r to float", key, raw)
                return _SENTINEL
        if expected_type is list:
            return [item.strip() for item in raw.split(",") if item.strip()]
        return raw

    def _load(self) -> None:
        stored: dict[str, Any] = {}
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as fh:
                    stored = json.load(fh)
            except (json.JSONDecodeError, OSError) as exc:
                log.warning("Config read failed (%s) — using defaults", exc)

        self._data = dict(self.DEFAULT_CONFIG)
        for key, value in stored.items():
            if key not in self.CONFIG_SCHEMA:
                continue
            try:
                self._validate(key, value)
                self._data[key] = value
            except TypeError:
                pass

        self.apply_env_overrides()
        self._save()

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, indent=2, default=str)
                fh.write("\n")
            tmp.replace(self._path)
        except OSError:
            if tmp.exists():
                tmp.unlink(missing_ok=True)

    def __repr__(self) -> str:
        return f"Config(path={self._path!s})"

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.set(key, value)
