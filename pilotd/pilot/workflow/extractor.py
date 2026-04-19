"""
Vision-based structured extraction.

Replaces the brittle ``read_as: pattern: "(regex)"`` path with a single
Claude call that sees the screenshot and answers a natural-language
question. Returns a typed value the workflow engine can store directly
in its run variables.

Why this exists: the OSU demo failed because the workflow asked for
'([0-9]+) swipes' but the phone showed 'Dining Dollars: $0.00'. The
concept matched (dining balance) — the literal text didn't. Vision
extraction answers 'What's the current balance?' and returns $0.00 as
a float, without the caller writing a regex.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import anthropic
from PIL import Image

from pilot import prompts
from pilot.core.usage import UsageTracker
from pilot.core.vision.json_extract import extract_json
from pilot.core.vision.agent import VisionAgent

log = logging.getLogger("pilotd.extractor")

_DEFAULT_CONFIDENCE_FLOOR = 0.6


class ExtractionError(RuntimeError):
    """Raised when the extraction LLM can't produce a valid typed answer."""


class VisionExtractor:
    """Single-field extractor — question + type in, typed value out."""

    def __init__(
        self,
        *,
        client: anthropic.Anthropic | None = None,
        fast_model: str = "claude-haiku-4-5-20251001",
        strong_model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 512,
        usage: UsageTracker | None = None,
    ) -> None:
        if client is None:
            key = os.environ.get("ANTHROPIC_API_KEY")
            if not key:
                raise ValueError("ANTHROPIC_API_KEY required for VisionExtractor")
            client = anthropic.Anthropic(api_key=key)
        self._client = client
        self._fast = fast_model
        self._strong = strong_model
        self._max_tokens = max_tokens
        self._usage = usage

    def extract(
        self,
        *,
        question: str,
        screenshot: Image.Image,
        expected_type: str = "string",
        hint: str | None = None,
        task_id: str | None = None,
    ) -> tuple[Any, float]:
        """Answer ``question`` against ``screenshot``. Returns (value, confidence).

        If the fast-model answer has confidence < 0.6, retries once with
        the strong model before accepting. Raises ExtractionError on a
        malformed LLM response.
        """
        value, confidence = self._one_shot(
            model=self._fast,
            question=question,
            screenshot=screenshot,
            expected_type=expected_type,
            hint=hint,
            task_id=task_id or "extract-fast",
        )
        if confidence < _DEFAULT_CONFIDENCE_FLOOR:
            log.info(
                "extractor: fast model confidence %.2f below floor, retrying with Sonnet",
                confidence,
            )
            value, confidence = self._one_shot(
                model=self._strong,
                question=question,
                screenshot=screenshot,
                expected_type=expected_type,
                hint=hint,
                task_id=task_id or "extract-strong",
            )
        return value, confidence

    def _one_shot(
        self,
        *,
        model: str,
        question: str,
        screenshot: Image.Image,
        expected_type: str,
        hint: str | None,
        task_id: str,
    ) -> tuple[Any, float]:
        system = prompts.get("EXTRACT_ANSWER")
        image_b64, media_type = VisionAgent._encode_image(
            VisionAgent.__new__(VisionAgent), screenshot,
        ) if False else _encode(screenshot)

        user_text = (
            f"Expected answer type: {expected_type}\n"
            f"Question: {question}\n"
        )
        if hint:
            user_text += f"Hint: {hint}\n"
        user_text += (
            "\nReturn JSON only: "
            '{"answer": <typed value or null>, "confidence": <0.0-1.0>, '
            '"reason": "<short why>"}.'
        )

        try:
            response = self._client.messages.create(
                model=model,
                max_tokens=self._max_tokens,
                system=system,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {"type": "image", "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_b64,
                        }},
                    ],
                }],
            )
        except anthropic.APIStatusError as exc:
            raise ExtractionError(f"extract API {exc.status_code}: {exc.message}") from exc

        if self._usage and hasattr(response, "usage") and response.usage is not None:
            self._usage.record_call(
                model=model,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                task_id=task_id,
            )

        text_blocks = [b.text for b in response.content if b.type == "text"]
        if not text_blocks:
            raise ExtractionError("empty LLM response")
        raw = text_blocks[0]

        try:
            data = extract_json(raw)
        except ValueError as exc:
            raise ExtractionError(f"could not parse JSON from: {raw[:200]}") from exc

        answer = data.get("answer")
        confidence = _clamp_float(data.get("confidence", 0.0))
        value = _coerce(answer, expected_type)
        return value, confidence


def _encode(image: Image.Image) -> tuple[str, str]:
    """Resize + JPEG-encode for Claude — same policy as VisionAgent."""
    import base64, io
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


def _clamp_float(v: Any) -> float:
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return 0.0


def _coerce(value: Any, expected_type: str) -> Any:
    """Type-coerce the LLM's answer. Returns None if coercion isn't possible."""
    if value is None:
        return None
    t = expected_type.lower()
    try:
        if t in ("int", "integer"):
            if isinstance(value, bool):
                return int(value)
            if isinstance(value, (int, float)):
                return int(value)
            if isinstance(value, str):
                cleaned = value.replace(",", "").replace("$", "").strip()
                return int(float(cleaned))
        if t in ("float", "number"):
            if isinstance(value, bool):
                return float(value)
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
                cleaned = value.replace(",", "").replace("$", "").strip()
                return float(cleaned)
        if t in ("bool", "boolean"):
            if isinstance(value, bool):
                return value
            if isinstance(value, (int, float)):
                return bool(value)
            if isinstance(value, str):
                return value.strip().lower() in ("true", "yes", "1", "on")
        if t == "list":
            if isinstance(value, list):
                return value
            if isinstance(value, str):
                return [x.strip() for x in value.split(",") if x.strip()]
        # default / string
        return str(value) if not isinstance(value, str) else value
    except (TypeError, ValueError):
        return None


__all__ = ["ExtractionError", "VisionExtractor"]
