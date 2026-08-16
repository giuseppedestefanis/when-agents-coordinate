"""Construction of a RunGraph from session files and the message log.

The graph combines two sources:

- The Claude Code session JSONL files give the agent-to-file and file-to-agent
  edges (file operations) and the per-turn token usage.
- The message protocol JSONL log, when present, gives the agent-to-agent edges
  (inter-agent messages). It is the clean source for that edge type. When no
  message log is supplied, agent-to-agent message edges are absent; sub-agent
  spawn edges are still recovered from Task tool calls.

Token attribution. A turn's output tokens are the cost of everything that turn
produced. The token_cost on an edge is that turn's output tokens divided
equally across the tool calls made in the turn. This is a coarse attribution.
The authoritative per-turn usage is written to turns.csv, and every edge
carries its turn_uuid, so a finer attribution can be done downstream.
"""

from __future__ import annotations

import os

from agent_comms.parser.addressing import normalise_target
from agent_comms.parser.model import (
    AGENT, AGENT_TO_AGENT, AGENT_TO_FILE, FILE, FILE_TO_AGENT, RunGraph,
)
from agent_comms.parser.sessions import extract, read_jsonl

FILE_WRITE_TOOLS = {"Write"}
FILE_EDIT_TOOLS = {"Edit", "NotebookEdit"}
FILE_READ_TOOLS = {"Read"}


def _utf8_len(value) -> int:
    return len(str(value).encode("utf-8"))


def _basename(path: str) -> str:
    return os.path.basename(path.rstrip("/")) or path


def build_graph(run_id, sessions, message_log=None, role_names=()):
    """Build the RunGraph for one run.

    sessions: list of {"agent_id": str, "path": str}.
    message_log: optional path to the message protocol JSONL log.
    role_names: iterable of addressable role-name strings for this
        run's task; an empty tuple by default (every Family 1 run).
        See agent_comms.parser.addressing for how role classification
        works on the message log.

    Returns (graph, turns).
    """
    graph = RunGraph(run_id)
    turns = []
    calls = []
    for session in sessions:
        session_turns, session_calls = extract(
            session["path"], session["agent_id"], run_id)
        turns.extend(session_turns)
        calls.extend(session_calls)

    for session in sessions:
        graph.ensure_node(session["agent_id"], AGENT, session["agent_id"])

    turn_by_uuid = {t.turn_uuid: t for t in turns}
    calls_per_turn: dict[str, int] = {}
    for call in calls:
        calls_per_turn[call.turn_uuid] = calls_per_turn.get(
            call.turn_uuid, 0) + 1

    def token_share(call) -> float:
        turn = turn_by_uuid.get(call.turn_uuid)
        count = calls_per_turn.get(call.turn_uuid, 1) or 1
        if turn is None:
            return 0.0
        return round(turn.output_tokens / count, 3)

    # Process calls in timestamp order so the first write to a path is a
    # create and later writes are edits.
    for call in sorted(calls, key=lambda c: c.timestamp):
        agent_node = call.agent
        if call.is_sidechain:
            agent_node = f"{call.agent}/sub"
            graph.ensure_node(agent_node, AGENT, agent_node)

        if call.tool in FILE_READ_TOOLS:
            path = call.input.get("file_path")
            if not path:
                continue
            graph.ensure_node(path, FILE, _basename(path))
            graph.add_edge(
                source=path, target=agent_node,
                source_type=FILE, target_type=AGENT,
                edge_type=FILE_TO_AGENT, subtype="read",
                timestamp=call.timestamp, token_cost=token_share(call),
                byte_size=call.result_bytes,
                turn_uuid=call.turn_uuid, tool=call.tool)

        elif call.tool in FILE_WRITE_TOOLS:
            path = call.input.get("file_path")
            if not path:
                continue
            subtype = "edit" if graph.has_node(path) else "create"
            graph.ensure_node(path, FILE, _basename(path))
            graph.add_edge(
                source=agent_node, target=path,
                source_type=AGENT, target_type=FILE,
                edge_type=AGENT_TO_FILE, subtype=subtype,
                timestamp=call.timestamp, token_cost=token_share(call),
                byte_size=_utf8_len(call.input.get("content", "")),
                turn_uuid=call.turn_uuid, tool=call.tool)

        elif call.tool in FILE_EDIT_TOOLS:
            path = call.input.get("file_path") or call.input.get(
                "notebook_path")
            if not path:
                continue
            graph.ensure_node(path, FILE, _basename(path))
            new_text = call.input.get(
                "new_string", call.input.get("new_source", ""))
            graph.add_edge(
                source=agent_node, target=path,
                source_type=AGENT, target_type=FILE,
                edge_type=AGENT_TO_FILE, subtype="edit",
                timestamp=call.timestamp, token_cost=token_share(call),
                byte_size=_utf8_len(new_text),
                turn_uuid=call.turn_uuid, tool=call.tool)

        elif call.tool == "Task":
            sub_node = f"{call.agent}/sub"
            graph.ensure_node(sub_node, AGENT, sub_node)
            graph.add_edge(
                source=call.agent, target=sub_node,
                source_type=AGENT, target_type=AGENT,
                edge_type=AGENT_TO_AGENT, subtype="spawn",
                timestamp=call.timestamp, token_cost=token_share(call),
                byte_size=_utf8_len(call.input.get("prompt", "")),
                turn_uuid=call.turn_uuid, tool=call.tool)

    if message_log:
        _add_message_edges(graph, message_log, role_names=role_names)
    return graph, turns


def _add_message_edges(graph, message_log, role_names=()) -> None:
    """Add agent-to-agent message edges from the message protocol log.

    The recipient field of each message event is classified by
    `normalise_target` into one of the five target kinds (canonical,
    alias, broadcast, role, unknown) and the edge's `target_kind`
    column records the classification. The graph node identity is
    the canonical form returned by normalisation, so aliases and
    canonical addresses share the same agent node and every broadcast
    collapses to one synthetic `*` node. Counting at the run level
    therefore stays event-by-event for the existing
    `n_agent_to_agent` column and the new `n_agent_to_agent_directed`
    column reports the addressed-to-a-specific-agent subset.
    """
    for event in read_jsonl(message_log):
        if event.get("event") != "message":
            continue
        sender = event.get("from")
        recipient_raw = event.get("to")
        if not sender or not recipient_raw:
            continue
        node_id, kind = normalise_target(recipient_raw, role_names)
        if not node_id:
            # Empty after normalisation (whitespace-only or None).
            continue
        graph.ensure_node(sender, AGENT, sender)
        graph.ensure_node(node_id, AGENT, node_id)
        graph.add_edge(
            source=sender, target=node_id,
            source_type=AGENT, target_type=AGENT,
            edge_type=AGENT_TO_AGENT, subtype="message",
            timestamp=event.get("ts", ""),
            token_cost=float(event.get("tokens_estimate", 0) or 0),
            byte_size=int(event.get("bytes", 0) or 0),
            turn_uuid="", tool="send_message",
            target_kind=kind)
