"""Message protocol (infrastructure component 1).

The protocol gives agents a typed channel for inter-agent communication so that
agent-to-agent edges in the communication graph can be measured cleanly and
separately from context handoffs.

- store.MessageStore: the core append-only message store. No third-party
  dependencies, so it can be tested without an MCP transport.
- server: a FastMCP server that wraps MessageStore and exposes send_message
  and check_messages to an agent.
"""
