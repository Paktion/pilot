"""Multi-strategy JSON extraction from free-form LLM text."""

from __future__ import annotations

import json
import re


def extract_json(text: str) -> dict:
    """Extract a JSON object from LLM text output using multiple strategies.

    Strategies tried in order:
      1. Strict ``json.loads`` on the full (stripped) text.
      2. Strip outer markdown code fences and retry.
      3. Find a ``json ... `` block anywhere in the text.
      4. Regex-find the first top-level ``{...}`` via brace-depth tracking.

    Raises ``ValueError`` if all strategies fail.
    """
    cleaned = text.strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    defenced = re.sub(r"^```(?:json)?\s*", "", cleaned)
    defenced = re.sub(r"\s*```\s*$", "", defenced)
    defenced = defenced.strip()
    if defenced != cleaned:
        try:
            return json.loads(defenced)
        except json.JSONDecodeError:
            pass

    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except json.JSONDecodeError:
            pass

    start = cleaned.find("{")
    if start != -1:
        depth = 0
        in_string = False
        escape_next = False
        for i in range(start, len(cleaned)):
            ch = cleaned[i]
            if escape_next:
                escape_next = False
                continue
            if ch == "\\":
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = cleaned[start : i + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        break

    raise ValueError(f"Could not extract JSON from LLM response. Raw text:\n{text}")
