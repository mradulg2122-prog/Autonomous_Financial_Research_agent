"""
Utility functions for ARA-1.
"""
from __future__ import annotations

import json
import re
from typing import Any


def parse_json_robustly(text: str | None) -> Any:
    """
    Parse a JSON string from a text block, handling:
    - None / empty responses from Gemini API
    - Markdown code blocks (```json ... ```)
    - Trailing garbage text after valid JSON
    - Leading preamble text before the JSON object/array
    """
    if not text or not text.strip():
        raise ValueError("Empty or None response from LLM — cannot parse JSON")

    text = text.strip()

    # 1. Try to strip markdown code fences
    code_fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.DOTALL)
    if code_fence:
        candidate = code_fence.group(1).strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass  # fall through to other methods

    # 2. Try raw parse (common case when response is clean JSON)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 3. Find first { or [ and extract balanced structure
    first_brace = text.find('{')
    first_bracket = text.find('[')

    if first_brace == -1 and first_bracket == -1:
        raise ValueError(f"No JSON object or array found in response: {text[:200]!r}")

    # Pick whichever comes first
    if first_brace != -1 and (first_bracket == -1 or first_brace < first_bracket):
        start_idx = first_brace
        open_char, close_char = '{', '}'
    else:
        start_idx = first_bracket
        open_char, close_char = '[', ']'

    depth = 0
    in_string = False
    escape = False

    for idx in range(start_idx, len(text)):
        ch = text[idx]
        if escape:
            escape = False
            continue
        if ch == '\\' and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if not in_string:
            if ch == open_char:
                depth += 1
            elif ch == close_char:
                depth -= 1
                if depth == 0:
                    candidate = text[start_idx:idx + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError as exc:
                        raise ValueError(f"Found JSON-like structure but failed to parse: {exc}") from exc

    raise ValueError(f"Unbalanced JSON structure in response: {text[:300]!r}")


def safe_serialize_message(msg: Any) -> dict:
    """
    Safely serialize an OpenAI message object to dict for the messages list.
    Handles both Gemini and OpenAI API response formats gracefully.
    """
    try:
        # Try model_dump first (Pydantic v2)
        dumped = msg.model_dump(exclude_none=True)
        # Gemini compat: ensure 'role' key exists
        if "role" not in dumped:
            dumped["role"] = "assistant"
        return dumped
    except Exception:
        pass

    try:
        # Fallback: manual extraction
        result: dict = {"role": getattr(msg, "role", "assistant")}
        if getattr(msg, "content", None):
            result["content"] = msg.content
        tool_calls = getattr(msg, "tool_calls", None)
        if tool_calls:
            result["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in tool_calls
            ]
        return result
    except Exception:
        return {"role": "assistant", "content": str(msg)}
