"""
Planner and authoring-assist helpers.

Everything here uses prompts loaded from the environment via
``pilot.prompts``. No prompt text lives in this module.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Callable

import anthropic

from pilot import prompts
from pilot.core.usage import UsageTracker
from pilot.core.vision.json_extract import extract_json

log = logging.getLogger("pilotd.planner")


class PlanError(RuntimeError):
    pass


@dataclass
class TaskStep:
    description: str
    status: str = "pending"  # pending | in_progress | completed | failed
    attempts: int = 0


@dataclass
class TaskPlan:
    original_task: str
    steps: list[TaskStep] = field(default_factory=list)
    current_index: int = 0

    @property
    def current_step(self) -> TaskStep | None:
        if 0 <= self.current_index < len(self.steps):
            return self.steps[self.current_index]
        return None

    @property
    def is_complete(self) -> bool:
        return self.current_index >= len(self.steps)

    @property
    def progress_pct(self) -> float:
        if not self.steps:
            return 0.0
        done = sum(1 for s in self.steps if s.status == "completed")
        return done / len(self.steps)


class Planner:
    """Claude-backed planner + authoring assistant."""

    def __init__(
        self,
        *,
        client: anthropic.Anthropic | None = None,
        sonnet_model: str = "claude-sonnet-4-20250514",
        haiku_model: str = "claude-haiku-4-5-20251001",
        max_tokens: int = 2048,
        usage: UsageTracker | None = None,
    ) -> None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if client is None and not api_key:
            raise ValueError("ANTHROPIC_API_KEY is required")
        self._client = client or anthropic.Anthropic(api_key=api_key)
        self.sonnet_model = sonnet_model
        self.haiku_model = haiku_model
        self.max_tokens = max_tokens
        self._usage = usage

    # ---- NL task -> 2-15 steps ----------------------------------------------

    def plan_task(self, task: str, memory_context: str = "") -> TaskPlan:
        system = prompts.get("TASK_PLANNER")
        if memory_context:
            system += (
                "\n\nRelevant prior context (use to prefer reliable paths, "
                "avoid previously failed approaches):\n" + memory_context
            )
        response = self._call(self.sonnet_model, system, task, task_id=f"plan:{task[:24]}")
        steps = _parse_step_list(response)
        if not steps:
            raise PlanError("planner returned no steps")
        return TaskPlan(original_task=task, steps=[TaskStep(description=s) for s in steps])

    # ---- NL description -> workflow YAML ------------------------------------

    def draft_workflow(self, description: str) -> str:
        system = prompts.get("DRAFT_WORKFLOW")
        response = self._call(
            self.sonnet_model, system, description, task_id="draft"
        )
        # Strip any accidental markdown fences.
        return _strip_fences(response)

    # ---- NL cadence -> cron expression (Haiku) ------------------------------

    def parse_cron(self, description: str) -> str:
        system = prompts.get("CRON_PARSE")
        response = self._call(self.haiku_model, system, description, task_id="cron")
        return response.strip().splitlines()[0].strip("` ")

    # ---- Failure diagnosis (Haiku) ------------------------------------------

    def diagnose_failure(self, run_context: str) -> str:
        system = prompts.get("DIAGNOSE_FAILURE")
        return self._call(self.haiku_model, system, run_context, task_id="diag").strip()

    # ---- internals ----------------------------------------------------------

    def _call(self, model: str, system: str, user_text: str, task_id: str) -> str:
        response = self._client.messages.create(
            model=model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_text}],
        )
        if self._usage and hasattr(response, "usage") and response.usage is not None:
            self._usage.record_call(
                model=model,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                task_id=task_id,
            )
        text_blocks = [b.text for b in response.content if b.type == "text"]
        if not text_blocks:
            raise PlanError("empty LLM response")
        return text_blocks[0]


def _parse_step_list(text: str) -> list[str]:
    """Best-effort extraction of a step list from the planner's response."""
    # Try JSON array first.
    try:
        data = extract_json(text)
        if isinstance(data, list):
            return [str(s) for s in data if str(s).strip()]
        if isinstance(data, dict) and "steps" in data:
            return [str(s) for s in data["steps"] if str(s).strip()]
    except ValueError:
        pass

    # Fall back to numbered lines: "1. Do X"
    out: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        # strip "- " "* " "1. " etc.
        for prefix in ("- ", "* "):
            if stripped.startswith(prefix):
                stripped = stripped[len(prefix):].strip()
                break
        if stripped[:2].isdigit():
            # trim leading numeric prefix like "12. "
            i = 0
            while i < len(stripped) and (stripped[i].isdigit() or stripped[i] in ".) "):
                i += 1
            stripped = stripped[i:].strip()
        if stripped:
            out.append(stripped)
    return out


def _strip_fences(text: str) -> str:
    import re
    out = text.strip()
    out = re.sub(r"^```(?:yaml|yml)?\s*", "", out)
    out = re.sub(r"\s*```\s*$", "", out)
    return out.strip()


__all__ = ["PlanError", "Planner", "TaskPlan", "TaskStep"]
