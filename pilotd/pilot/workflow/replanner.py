"""
Replan on step failure.

When a workflow step fails — ``wait_for`` timed out, ``tap_text`` couldn't
find the target, ``extract`` couldn't answer — the engine asks Claude:
"given what you're seeing right now and what just broke, produce a new
list of steps that gets us back on track."

The replanner returns a ``list[Step]`` that the engine splices in at the
failed index. Per-run replan budget prevents infinite retry loops.
"""

from __future__ import annotations

import base64
import io
import logging
import os
import re
from typing import TYPE_CHECKING, Any

import anthropic
import yaml
from PIL import Image

from pilot import prompts
from pilot.core.usage import UsageTracker
from pilot.workflow.schema import Step, WorkflowDef, WorkflowParseError, parse_workflow_yaml

if TYPE_CHECKING:
    pass

log = logging.getLogger("pilotd.replanner")

DEFAULT_REPLAN_BUDGET = 3


class ReplanRejected(RuntimeError):
    """Replan output couldn't be parsed into valid workflow steps."""


class Replanner:
    """Claude-backed corrective planner that produces replacement steps."""

    def __init__(
        self,
        *,
        client: anthropic.Anthropic | None = None,
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 1024,
        usage: UsageTracker | None = None,
    ) -> None:
        if client is None:
            key = os.environ.get("ANTHROPIC_API_KEY")
            if not key:
                raise ValueError("ANTHROPIC_API_KEY required for Replanner")
            client = anthropic.Anthropic(api_key=key)
        self._client = client
        self._model = model
        self._max_tokens = max_tokens
        self._usage = usage

    def replan(
        self,
        *,
        defn: WorkflowDef,
        failed_step: Step,
        failed_idx: int,
        error: str,
        screenshot: Image.Image,
        variables: dict[str, Any],
        task_id: str,
    ) -> list[Step]:
        """Return a fresh list of replacement steps to splice in at ``failed_idx``."""
        system = prompts.get("REPLAN")

        completed_desc = self._summarize_progress(defn, failed_idx)
        user_text = (
            f"Workflow: {defn.name}\n"
            f"App: {defn.app or '(unspecified)'}\n"
            f"Description: {defn.description}\n\n"
            f"Completed steps so far:\n{completed_desc}\n\n"
            f"Failed step (index {failed_idx}): {failed_step.kind.value} "
            f"— data: {_describe_step(failed_step)}\n"
            f"Error: {error}\n\n"
            f"Current workflow variables: {_summarize_vars(variables)}\n\n"
            "The screenshot is attached — look at the actual phone screen.\n\n"
            "Produce ONLY a YAML step list under a top-level 'steps:' key. "
            "No fences, no workflow envelope. Prefer 1-3 steps that recover "
            "and continue. If unreachable, emit a single done step with a "
            "summary explaining why."
        )

        image_b64, media_type = _encode(screenshot)
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {"type": "image", "source": {
                            "type": "base64", "media_type": media_type,
                            "data": image_b64,
                        }},
                    ],
                }],
            )
        except anthropic.APIStatusError as exc:
            raise ReplanRejected(
                f"replan API {exc.status_code}: {exc.message}"
            ) from exc

        if self._usage and hasattr(response, "usage") and response.usage is not None:
            self._usage.record_call(
                model=self._model,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                task_id=task_id,
            )

        text_blocks = [b.text for b in response.content if b.type == "text"]
        if not text_blocks:
            raise ReplanRejected("replan returned no text")
        raw_yaml = _strip_fences(text_blocks[0])

        new_steps = self._parse_replacement_steps(raw_yaml, defn)
        log.info(
            "replan for %s[%d]: %d new steps (error=%s)",
            defn.name, failed_idx, len(new_steps), error[:80],
        )
        return new_steps

    @staticmethod
    def _summarize_progress(defn: WorkflowDef, failed_idx: int) -> str:
        if failed_idx <= 0:
            return "  (none — failed on first step)"
        lines: list[str] = []
        for i in range(failed_idx):
            s = defn.steps[i]
            lines.append(f"  [{i}] {s.kind.value} — {_describe_step(s)}")
        return "\n".join(lines)

    @staticmethod
    def _parse_replacement_steps(raw_yaml: str, defn: WorkflowDef) -> list[Step]:
        """Wrap the LLM's step list in a fake envelope + reuse our YAML parser."""
        trimmed = raw_yaml.strip()
        if not trimmed.startswith("steps:"):
            # The LLM may have returned a bare list of steps without the
            # 'steps:' key — try to normalize.
            if trimmed.startswith("- "):
                trimmed = "steps:\n" + "\n".join(f"  {ln}" for ln in trimmed.splitlines())
            else:
                raise ReplanRejected(
                    f"replan output missing 'steps:' envelope:\n{trimmed[:240]}"
                )
        fake = f"name: _replan_{defn.slug}\napp: {defn.app or 'unknown'}\n{trimmed}\n"
        try:
            fake_defn = parse_workflow_yaml(fake)
        except WorkflowParseError as exc:
            raise ReplanRejected(f"replan YAML invalid: {exc}") from exc
        return fake_defn.steps


def _describe_step(step: Step) -> str:
    if step.primary:
        return f"primary={step.primary!r}"
    return f"data={dict((k, v) for k, v in step.data.items() if not k.startswith('_'))}"


def _summarize_vars(vars: dict[str, Any]) -> str:
    if not vars:
        return "(none)"
    items = []
    for k, v in vars.items():
        if k.startswith("_"):
            continue
        s = str(v)
        items.append(f"{k}={s[:40]}")
    return ", ".join(items) or "(none)"


def _strip_fences(text: str) -> str:
    out = text.strip()
    out = re.sub(r"^```(?:yaml|yml)?\s*", "", out)
    out = re.sub(r"\s*```\s*$", "", out)
    return out.strip()


def _encode(image: Image.Image) -> tuple[str, str]:
    from PIL.Image import LANCZOS
    MAX = 1568
    img = image
    if max(img.size) > MAX:
        img = img.copy()
        img.thumbnail((MAX, MAX), LANCZOS)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    buf.seek(0)
    return base64.standard_b64encode(buf.read()).decode("ascii"), "image/jpeg"


__all__ = ["DEFAULT_REPLAN_BUDGET", "ReplanRejected", "Replanner"]
