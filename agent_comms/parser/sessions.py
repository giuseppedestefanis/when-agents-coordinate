"""Extraction of turns and tool calls from a Claude Code session JSONL file.

A session JSONL file has one JSON object per line. The line types relevant to
the communication graph are:

- "assistant": one model turn. Carries message.usage (token counts) and a
  message.content list that may contain tool_use blocks.
- "user": carries tool_result blocks in message.content, which give the size
  of each tool call's result.

The isSidechain flag marks lines that belong to a spawned sub-agent rather
than the main session.
"""

from __future__ import annotations

import json

from agent_comms.parser.model import Turn


def read_jsonl(path):
    """Yield the JSON object on each non-blank line of a JSONL file."""
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def _content_size(content) -> int:
    """Return the UTF-8 byte size of a tool_result content field.

    The content may be a plain string or a list of content blocks.
    """
    if isinstance(content, str):
        return len(content.encode("utf-8"))
    if isinstance(content, list):
        total = 0
        for block in content:
            if isinstance(block, dict):
                total += len(str(block.get("text", "")).encode("utf-8"))
            else:
                total += len(str(block).encode("utf-8"))
        return total
    return 0


class ToolCall:
    """One tool_use block, with the size of its result once known."""

    def __init__(self, agent, tool, tool_id, tool_input, timestamp,
                 turn_uuid, is_sidechain):
        self.agent = agent
        self.tool = tool
        self.tool_id = tool_id
        self.input = tool_input
        self.timestamp = timestamp
        self.turn_uuid = turn_uuid
        self.is_sidechain = is_sidechain
        self.result_bytes = 0


def extract(path, agent_id, run_id):
    """Return (turns, tool_calls) extracted from one session JSONL file.

    turns is a list of Turn. tool_calls is a list of ToolCall, each with its
    result_bytes filled in from the matching tool_result.
    """
    turns: list[Turn] = []
    calls: list[ToolCall] = []
    result_sizes: dict[str, int] = {}

    for obj in read_jsonl(path):
        line_type = obj.get("type")
        message = obj.get("message")
        if line_type == "assistant" and isinstance(message, dict):
            usage = message.get("usage") or {}
            turn_uuid = obj.get("uuid", "")
            timestamp = obj.get("timestamp", "")
            is_sidechain = bool(obj.get("isSidechain"))
            turns.append(Turn(
                run_id=run_id,
                agent=agent_id,
                turn_uuid=turn_uuid,
                timestamp=timestamp,
                is_sidechain=is_sidechain,
                input_tokens=usage.get("input_tokens", 0) or 0,
                output_tokens=usage.get("output_tokens", 0) or 0,
                cache_read_tokens=usage.get("cache_read_input_tokens", 0) or 0,
                cache_creation_tokens=usage.get(
                    "cache_creation_input_tokens", 0) or 0,
                model=message.get("model", ""),
            ))
            content = message.get("content")
            if isinstance(content, list):
                for block in content:
                    if (isinstance(block, dict)
                            and block.get("type") == "tool_use"):
                        calls.append(ToolCall(
                            agent=agent_id,
                            tool=block.get("name", ""),
                            tool_id=block.get("id", ""),
                            tool_input=block.get("input") or {},
                            timestamp=timestamp,
                            turn_uuid=turn_uuid,
                            is_sidechain=is_sidechain,
                        ))
        elif line_type == "user" and isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, list):
                for block in content:
                    if (isinstance(block, dict)
                            and block.get("type") == "tool_result"):
                        tool_id = block.get("tool_use_id", "")
                        result_sizes[tool_id] = _content_size(
                            block.get("content"))

    for call in calls:
        call.result_bytes = result_sizes.get(call.tool_id, 0)
    return turns, calls
