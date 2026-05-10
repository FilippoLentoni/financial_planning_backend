from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any


def iter_lines(streaming_body: Any) -> Iterator[str]:
    if hasattr(streaming_body, "iter_lines"):
        for raw in streaming_body.iter_lines(chunk_size=65536, keepends=False):
            if raw is None:
                continue
            yield raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
    else:
        body = getattr(streaming_body, "read", lambda: streaming_body)()
        if isinstance(body, (bytes, bytearray)):
            body = body.decode("utf-8", errors="replace")
        for line in str(body).splitlines():
            yield line


def iter_objects(streaming_body: Any) -> Iterator[dict[str, Any]]:
    for line in iter_lines(streaming_body):
        item = line.strip()
        if not item:
            continue
        if item.startswith("data:"):
            item = item[len("data:") :].lstrip()
        if item.startswith(("event:", "id:", "retry:", ":")):
            continue
        try:
            parsed = json.loads(item)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            yield parsed


def extract_text(event: dict[str, Any]) -> str:
    delta = event.get("delta")
    if isinstance(delta, dict) and isinstance(delta.get("text"), str):
        return delta["text"]

    nested_delta = (
        event.get("event", {})
        .get("contentBlockDelta", {})
        .get("delta", {})
    )
    if isinstance(nested_delta, dict) and isinstance(nested_delta.get("text"), str):
        return nested_delta["text"]

    message = event.get("message")
    if isinstance(message, dict):
        parts: list[str] = []
        for block in message.get("content") or []:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "".join(parts)

    return ""


def extract_response_text(events: Iterator[dict[str, Any]]) -> str:
    delta_parts: list[str] = []
    final_messages: list[str] = []

    for event in events:
        message = event.get("message")
        if isinstance(message, dict):
            parts: list[str] = []
            for block in message.get("content") or []:
                if isinstance(block, dict) and isinstance(block.get("text"), str):
                    parts.append(block["text"])
            if parts:
                final_messages.append("".join(parts))
                continue

        text = extract_text(event)
        if text:
            delta_parts.append(text)

    if final_messages:
        return final_messages[-1].strip()
    return "".join(delta_parts).strip()
