"""MCP server exposing the agent communication protocol.

Each agent in a run launches this server, configured through environment
variables with its own identity and the shared run log. The server exposes two
tools, send_message and check_messages. Every call is recorded in the shared
JSONL log by the underlying MessageStore.

Environment variables:
  AGENT_COMMS_SELF    the calling agent's identifier, for example "agent-1"
                      (required).
  AGENT_COMMS_LOG     path to the shared run log JSONL file (required).
  AGENT_COMMS_RUN     the run identifier recorded in every event (optional).
  AGENT_COMMS_ROSTER  comma-separated list of valid agent identifiers
                      (optional).

The server is launched per agent, for example with
  python -m agent_comms.message_protocol.server
"""

from __future__ import annotations

import json
import os

from mcp.server.fastmcp import FastMCP

from agent_comms.message_protocol.store import (
    MessageProtocolError, MessageStore,
)

mcp = FastMCP("agent-comms-message-protocol")


def _store_from_env() -> MessageStore:
    log = os.environ.get("AGENT_COMMS_LOG")
    if not log:
        raise RuntimeError("AGENT_COMMS_LOG environment variable is required")
    roster_env = os.environ.get("AGENT_COMMS_ROSTER", "")
    roster = [a.strip() for a in roster_env.split(",") if a.strip()] or None
    return MessageStore(
        log, run_id=os.environ.get("AGENT_COMMS_RUN", ""), roster=roster)


def _self_id() -> str:
    self_id = os.environ.get("AGENT_COMMS_SELF")
    if not self_id:
        raise RuntimeError("AGENT_COMMS_SELF environment variable is required")
    return self_id


@mcp.tool()
def send_message(to_agent: str, content: str) -> str:
    """Send a message to another agent working on the shared task.

    to_agent: the identifier of the recipient agent.
    content: the message text.
    """
    store = _store_from_env()
    try:
        event = store.send(_self_id(), to_agent, content)
    except MessageProtocolError as exc:
        return f"Message not sent: {exc}"
    return f"Message {event['seq']} delivered to {to_agent}."


@mcp.tool()
def check_messages() -> str:
    """Return messages addressed to you that you have not yet received."""
    store = _store_from_env()
    delivered = store.poll(_self_id())
    if not delivered:
        return "No new messages."
    return json.dumps(
        [{"from": e["from"], "content": e["content"], "ts": e["ts"]}
         for e in delivered],
        ensure_ascii=False, indent=2)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
