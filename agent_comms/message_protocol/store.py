"""Core message store for the agent communication protocol.

This module has no third-party dependencies. The MCP server in server.py is a
thin wrapper around MessageStore, so the store can be exercised directly in
tests without an MCP transport.

A run's messages are kept in a single append-only JSONL event log. Every
send_message call appends one "message" event and every poll appends one
"poll" event. The log is the authoritative record from which the session
parser builds the agent-to-agent edges of the communication graph.

Each event carries a monotonically increasing integer "seq" equal to its line
index in the log. Per-agent read cursors are kept in sidecar files next to the
log so that several agent processes, each with its own MessageStore on the
shared log, can poll without re-receiving messages. All reads and writes are
serialised with an exclusive file lock, so concurrent agent processes do not
corrupt the log or miss messages.
"""

from __future__ import annotations

import fcntl
import json
import os
from datetime import datetime, timezone


def _utc_now() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def estimate_tokens(content: str) -> int:
    """Return a rough token estimate for a string.

    The heuristic is about four characters per token. The authoritative token
    cost for an edge comes from the Claude Code session JSONL through the
    session parser; this estimate is only a fallback recorded with each event.
    """
    return max(1, round(len(content) / 4))


class MessageProtocolError(ValueError):
    """Raised when a message fails validation."""


class _FileLock:
    """Exclusive lock over a run's message log, scoped to a with-block."""

    def __init__(self, path: str):
        self._path = path
        self._fh = None

    def __enter__(self):
        self._fh = open(self._path, "w")
        fcntl.flock(self._fh, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        fcntl.flock(self._fh, fcntl.LOCK_UN)
        self._fh.close()
        self._fh = None


class MessageStore:
    """Append-only store of inter-agent messages for one run.

    log_path: path to the run's JSONL log. Created, with parent directories,
        if it does not exist.
    run_id: identifier recorded in every event.
    roster: optional iterable of valid agent identifiers. When given, messages
        to or from an identifier outside the roster are still recorded but are
        flagged with "unknown_recipient" or "unknown_sender".
    """

    def __init__(self, log_path, run_id: str = "", roster=None):
        self.log_path = os.fspath(log_path)
        self.run_id = run_id
        self.roster = set(roster) if roster is not None else None
        os.makedirs(os.path.dirname(self.log_path) or ".", exist_ok=True)
        self._lock_path = self.log_path + ".lock"

    # -- internal io ----------------------------------------------------------

    def _read_events(self) -> list:
        if not os.path.exists(self.log_path):
            return []
        events = []
        with open(self.log_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    events.append(json.loads(line))
        return events

    def _append(self, event: dict) -> None:
        with open(self.log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _cursor_path(self, agent: str) -> str:
        return f"{self.log_path}.cursor-{agent}"

    def _read_cursor(self, agent: str) -> int:
        path = self._cursor_path(agent)
        if not os.path.exists(path):
            return -1
        with open(path, "r", encoding="utf-8") as fh:
            return int(fh.read().strip() or "-1")

    def _write_cursor(self, agent: str, seq: int) -> None:
        with open(self._cursor_path(agent), "w", encoding="utf-8") as fh:
            fh.write(str(seq))

    # -- public api -----------------------------------------------------------

    def send(self, from_agent: str, to_agent: str, content: str) -> dict:
        """Record a message from from_agent to to_agent and return its event."""
        if not isinstance(from_agent, str) or not from_agent:
            raise MessageProtocolError("from_agent must be a non-empty string")
        if not isinstance(to_agent, str) or not to_agent:
            raise MessageProtocolError("to_agent must be a non-empty string")
        if not isinstance(content, str):
            raise MessageProtocolError("content must be a string")
        if from_agent == to_agent:
            raise MessageProtocolError(
                "an agent cannot send a message to itself")
        with _FileLock(self._lock_path):
            seq = len(self._read_events())
            event = {
                "event": "message",
                "seq": seq,
                "run": self.run_id,
                "from": from_agent,
                "to": to_agent,
                "content": content,
                "bytes": len(content.encode("utf-8")),
                "tokens_estimate": estimate_tokens(content),
                "ts": _utc_now(),
            }
            if self.roster is not None:
                if to_agent not in self.roster:
                    event["unknown_recipient"] = True
                if from_agent not in self.roster:
                    event["unknown_sender"] = True
            self._append(event)
        return event

    def poll(self, agent: str) -> list:
        """Return message events addressed to agent not yet delivered to it.

        Advances the agent's read cursor and records a "poll" event.
        """
        if not isinstance(agent, str) or not agent:
            raise MessageProtocolError("agent must be a non-empty string")
        with _FileLock(self._lock_path):
            cursor = self._read_cursor(agent)
            events = self._read_events()
            delivered = [
                e for e in events
                if e["seq"] > cursor
                and e.get("event") == "message"
                and e.get("to") == agent
            ]
            poll_seq = len(events)
            poll_event = {
                "event": "poll",
                "seq": poll_seq,
                "run": self.run_id,
                "agent": agent,
                "delivered": len(delivered),
                "ts": _utc_now(),
            }
            self._append(poll_event)
            self._write_cursor(agent, poll_seq)
        return delivered

    def events(self) -> list:
        """Return every event in the log, in order."""
        with _FileLock(self._lock_path):
            return self._read_events()
