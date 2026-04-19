"""
VisionAgent — Anthropic client that turns (screenshot, task) into one action.

Supports two paths:
  * tool-use mode (default) — structured tool calls, no JSON parsing failures
  * JSON mode (legacy)      — free-form JSON fallback with multi-strategy parse

System prompts are loaded from environment via ``pilot.prompts`` so no prompt
text lives in the source tree.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import time
from typing import Any

import anthropic
from PIL import Image

from pilot import prompts
from pilot.core.vision.actions import (
    ActionType,
    AgentResponse,
    LowConfidenceError,
    parse_action,
)
from pilot.core.vision.json_extract import extract_json
from pilot.core.vision.tools import TOOL_DEFINITIONS, TOOL_NAME_TO_ACTION_TYPE

log = logging.getLogger("pilotd.vision")

_MAX_IMAGE_DIMENSION = 1568
_DEFAULT_JPEG_QUALITY = 85
_DEFAULT_CONFIDENCE_THRESHOLD = 0.5
_DEFAULT_MAX_RETRIES = 3
_DEFAULT_RETRY_DELAY = 1.0


class VisionAgent:
    """Multimodal LLM agent — interprets screenshots and emits one action."""

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        api_key: str | None = None,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        retry_delay: float = _DEFAULT_RETRY_DELAY,
        max_tokens: int = 4096,
        use_tool_mode: bool = True,
        confidence_threshold: float = _DEFAULT_CONFIDENCE_THRESHOLD,
        jpeg_quality: int = _DEFAULT_JPEG_QUALITY,
    ) -> None:
        self.model = model
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.max_tokens = max_tokens
        self.use_tool_mode = use_tool_mode
        self.confidence_threshold = confidence_threshold
        self.jpeg_quality = jpeg_quality

        api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError(
                "No Anthropic API key found. Set ANTHROPIC_API_KEY in your "
                "environment or .env file. Get a key at "
                "https://console.anthropic.com/settings/keys"
            )
        self.client = anthropic.Anthropic(api_key=api_key)
        self.last_usage: dict[str, int] | None = None
        log.info("VisionAgent ready (model=%s, tool_mode=%s)", model, use_tool_mode)

    def analyze_screen(
        self,
        screenshot: Image.Image,
        task: str,
        history: list[dict] | None = None,
    ) -> AgentResponse:
        if self.use_tool_mode:
            return self._analyze_tool_use(screenshot, task, history)
        return self._analyze_json(screenshot, task, history)

    def _analyze_json(
        self,
        screenshot: Image.Image,
        task: str,
        history: list[dict] | None,
    ) -> AgentResponse:
        messages = self._build_messages(screenshot, task, history)
        system_prompt = self._system_prompt_with_dims(screenshot)
        response_text = self._call_api(system_prompt, messages)
        result = self._parse_json_response(response_text)
        self._check_confidence(result)
        return result

    def _analyze_tool_use(
        self,
        screenshot: Image.Image,
        task: str,
        history: list[dict] | None,
    ) -> AgentResponse:
        messages = self._build_messages(screenshot, task, history)
        system_prompt = self._system_prompt_with_dims(screenshot)
        response = self._call_api_tool_use(system_prompt, messages)
        result = self._parse_tool_use_response(response)
        self._check_confidence(result)
        return result

    def _system_prompt_with_dims(self, screenshot: Image.Image) -> str:
        base = prompts.get("AGENT_SYSTEM")
        # Report the ACTUAL dimensions Claude will see after client-side
        # resize, not the original capture. Lying about the size shifts
        # tap coordinates by the resize ratio — that bug cost us hours.
        width, height = screenshot.size
        if max(width, height) > _MAX_IMAGE_DIMENSION:
            if width >= height:
                new_w = _MAX_IMAGE_DIMENSION
                new_h = int(height * _MAX_IMAGE_DIMENSION / width)
            else:
                new_h = _MAX_IMAGE_DIMENSION
                new_w = int(width * _MAX_IMAGE_DIMENSION / height)
            width, height = new_w, new_h
        return base + (
            f"\n\nThe current screenshot is {width}x{height} pixels. "
            f"All coordinates must be within x in [0, {width - 1}], "
            f"y in [0, {height - 1}]."
        )

    def _build_messages(
        self,
        screenshot: Image.Image,
        task: str,
        history: list[dict] | None,
    ) -> list[dict]:
        messages: list[dict] = []
        if history:
            for entry in history:
                role = entry.get("role", "user")
                content = entry.get("content", "")
                if isinstance(content, (dict, list)):
                    content = json.dumps(content, ensure_ascii=False)
                if messages and messages[-1]["role"] == role:
                    prev = messages[-1]["content"]
                    if isinstance(prev, str) and isinstance(content, str):
                        messages[-1]["content"] = prev + "\n" + content
                    continue
                messages.append({"role": role, "content": content})

        image_data, media_type = self._encode_image(screenshot)
        width, height = screenshot.size
        user_content: list[dict] = [
            {
                "type": "text",
                "text": (
                    f"Task: {task}\n\n"
                    f"The screenshot is {width}x{height} pixels.\n"
                    "Analyze what you see and respond with your next action."
                ),
            },
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": image_data,
                },
            },
        ]
        messages.append({"role": "user", "content": user_content})
        return messages

    def _call_api(self, system_prompt: str, messages: list[dict]) -> str:
        delay = self.retry_delay
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    system=system_prompt,
                    messages=messages,
                )
                self._record_usage(response)
                text_blocks = [b.text for b in response.content if b.type == "text"]
                if not text_blocks:
                    raise ValueError("LLM response contained no text blocks.")
                return text_blocks[0]
            except anthropic.APIStatusError as exc:
                if exc.status_code in (429, 500, 502, 503, 529) and attempt < self.max_retries:
                    log.warning("API %d — retrying in %.1fs", exc.status_code, delay)
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise
            except anthropic.APIConnectionError:
                if attempt < self.max_retries:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise
        raise RuntimeError("Exhausted all API retry attempts")

    def _call_api_tool_use(
        self, system_prompt: str, messages: list[dict]
    ) -> anthropic.types.Message:
        delay = self.retry_delay
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    system=system_prompt,
                    messages=messages,
                    tools=TOOL_DEFINITIONS,
                    tool_choice={"type": "any"},
                )
                self._record_usage(response)
                return response
            except anthropic.APIStatusError as exc:
                if exc.status_code in (429, 500, 502, 503, 529) and attempt < self.max_retries:
                    log.warning("API %d — retrying in %.1fs", exc.status_code, delay)
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise
            except anthropic.APIConnectionError:
                if attempt < self.max_retries:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise
        raise RuntimeError("Exhausted all API retry attempts")

    def _record_usage(self, response: Any) -> None:
        if hasattr(response, "usage") and response.usage is not None:
            self.last_usage = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            }
        else:
            self.last_usage = None

    def _parse_json_response(self, response_text: str) -> AgentResponse:
        data = extract_json(response_text)
        thought = data.get("thought", "")
        confidence = self._parse_confidence(data.get("confidence", 0.5))
        action_data = data.get("action")
        if not isinstance(action_data, dict):
            raise ValueError(f"Missing 'action' dict in response: {type(action_data).__name__}")
        return AgentResponse(thought=thought, action=parse_action(action_data), confidence=confidence)

    def _parse_tool_use_response(self, response: anthropic.types.Message) -> AgentResponse:
        tool_block = None
        text_parts: list[str] = []
        for block in response.content:
            if block.type == "tool_use" and tool_block is None:
                tool_block = block
            elif block.type == "text":
                text_parts.append(block.text)

        if tool_block is None:
            if text_parts:
                return self._parse_json_response("\n".join(text_parts))
            raise ValueError("Response contained no tool_use or text blocks.")

        tool_input = tool_block.input
        thought = tool_input.get("thought") or ("\n".join(text_parts) if text_parts else "")
        confidence = self._parse_confidence(tool_input.get("confidence", 0.5))
        action_type = TOOL_NAME_TO_ACTION_TYPE.get(tool_block.name)
        if action_type is None:
            raise ValueError(f"Unknown tool '{tool_block.name}'")

        meta = {"thought", "confidence"}
        action_data: dict[str, Any] = {"type": action_type}
        for key, value in tool_input.items():
            if key not in meta:
                action_data[key] = value
        action_data["step_complete"] = bool(action_data.get("step_complete", False))
        return AgentResponse(thought=thought, action=parse_action(action_data), confidence=confidence)

    @staticmethod
    def _parse_confidence(raw: object) -> float:
        try:
            return max(0.0, min(1.0, float(raw)))
        except (TypeError, ValueError):
            return 0.5

    def _check_confidence(self, result: AgentResponse) -> None:
        if result.confidence < self.confidence_threshold:
            raise LowConfidenceError(
                f"Confidence {result.confidence:.2f} < threshold "
                f"{self.confidence_threshold:.2f}: {result.thought}",
                response=result,
            )

    def _encode_image(self, image: Image.Image) -> tuple[str, str]:
        if max(image.size) > _MAX_IMAGE_DIMENSION:
            image = image.copy()
            image.thumbnail((_MAX_IMAGE_DIMENSION, _MAX_IMAGE_DIMENSION), Image.LANCZOS)
        if image.mode in ("RGBA", "LA", "P"):
            image = image.convert("RGB")
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=self.jpeg_quality)
        buffer.seek(0)
        return base64.standard_b64encode(buffer.read()).decode("ascii"), "image/jpeg"

    @staticmethod
    def build_history_entry(
        role: str, thought: str, action: ActionType, confidence: float
    ) -> dict:
        action_dict = {k: v for k, v in action.__dict__.items() if v is not None}
        payload = {"thought": thought, "action": action_dict, "confidence": confidence}
        return {"role": role, "content": json.dumps(payload, ensure_ascii=False)}
