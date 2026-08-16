"""Tests for the session parser (infrastructure component 2).

These exercise the parser on synthetic session JSONL fixtures that follow the
Claude Code session format: assistant lines with usage and tool_use blocks,
user lines with tool_result blocks. They confirm that the graph nodes and
edges are built correctly, that token cost is attributed, and that the CSV
datasets are written and can be read back.

Run with: pytest tests/test_parser.py
"""

import csv
import json
import os

from agent_comms.parser import build_graph, combine_datasets, parse_run


def write_jsonl(path, objs):
    with open(path, "w", encoding="utf-8") as fh:
        for obj in objs:
            fh.write(json.dumps(obj) + "\n")


def assistant(uuid, ts, content, output_tokens, input_tokens=100,
              sidechain=False):
    return {
        "type": "assistant", "uuid": uuid, "timestamp": ts,
        "isSidechain": sidechain,
        "message": {
            "model": "claude-test", "role": "assistant", "content": content,
            "usage": {
                "input_tokens": input_tokens, "output_tokens": output_tokens,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
            },
        },
    }


def tool_use(uid, name, tool_input):
    return {"type": "tool_use", "id": uid, "name": name, "input": tool_input}


def user_results(results):
    return {
        "type": "user",
        "message": {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": tid, "content": body}
                for tid, body in results
            ],
        },
    }


def make_session(path):
    """A two-turn session: create solution.py, then read spec.md and edit."""
    write_jsonl(path, [
        {"type": "user", "message": {"role": "user", "content": "go"}},
        assistant("t1", "2026-05-22T10:00:00.000Z",
                  [tool_use("u1", "Write",
                            {"file_path": "/w/solution.py",
                             "content": "print(1)"})],
                  output_tokens=40),
        user_results([("u1", "File created at /w/solution.py")]),
        assistant("t2", "2026-05-22T10:00:30.000Z",
                  [tool_use("u2", "Read", {"file_path": "/w/spec.md"}),
                   tool_use("u3", "Edit",
                            {"file_path": "/w/solution.py",
                             "old_string": "1", "new_string": "2"})],
                  output_tokens=60),
        user_results([("u2", "spec contents here"),
                      ("u3", "edit applied")]),
    ])


def sessions_for(tmp_path):
    session_path = tmp_path / "agent-1.jsonl"
    make_session(session_path)
    return [{"agent_id": "agent-1", "path": str(session_path)}]


# --- graph construction ------------------------------------------------------

def test_builds_agent_and_file_nodes(tmp_path):
    graph, _ = build_graph("run1", sessions_for(tmp_path))
    types = {n.node_id: n.node_type for n in graph.nodes.values()}
    assert types["agent-1"] == "agent"
    assert types["/w/solution.py"] == "file"
    assert types["/w/spec.md"] == "file"


def test_first_write_is_create_second_is_edit(tmp_path):
    graph, _ = build_graph("run1", sessions_for(tmp_path))
    solution_edges = [e for e in graph.edges
                      if e.target == "/w/solution.py"]
    assert [e.subtype for e in solution_edges] == ["create", "edit"]


def test_read_is_file_to_agent_edge(tmp_path):
    graph, _ = build_graph("run1", sessions_for(tmp_path))
    reads = [e for e in graph.edges if e.subtype == "read"]
    assert len(reads) == 1
    assert reads[0].source == "/w/spec.md"
    assert reads[0].target == "agent-1"
    assert reads[0].edge_type == "file_to_agent"


def test_token_cost_split_across_turn_tool_calls(tmp_path):
    graph, _ = build_graph("run1", sessions_for(tmp_path))
    by_turn = {}
    for edge in graph.edges:
        by_turn.setdefault(edge.turn_uuid, []).append(edge.token_cost)
    # turn t1 had one tool call: full 40 output tokens
    assert by_turn["t1"] == [40.0]
    # turn t2 had two tool calls: 60 output tokens split equally
    assert by_turn["t2"] == [30.0, 30.0]


def test_byte_sizes(tmp_path):
    graph, _ = build_graph("run1", sessions_for(tmp_path))
    by_subtype = {e.subtype: e for e in graph.edges}
    assert by_subtype["create"].byte_size == len("print(1)")
    assert by_subtype["read"].byte_size == len("spec contents here")
    assert by_subtype["edit"].byte_size == len("2")


def test_turns_carry_usage(tmp_path):
    _, turns = build_graph("run1", sessions_for(tmp_path))
    assert len(turns) == 2
    assert sum(t.output_tokens for t in turns) == 100
    assert sum(t.input_tokens for t in turns) == 200


# --- message log integration -------------------------------------------------

def test_message_log_adds_agent_to_agent_edges(tmp_path):
    message_log = tmp_path / "messages.jsonl"
    write_jsonl(message_log, [
        {"event": "message", "seq": 0, "run": "run1", "from": "agent-1",
         "to": "agent-2", "content": "hi", "bytes": 2, "tokens_estimate": 1,
         "ts": "2026-05-22T10:00:10.000Z"},
        {"event": "poll", "seq": 1, "run": "run1", "agent": "agent-2",
         "delivered": 1, "ts": "2026-05-22T10:00:11.000Z"},
    ])
    graph, _ = build_graph("run1", sessions_for(tmp_path),
                           message_log=str(message_log))
    messages = [e for e in graph.edges if e.subtype == "message"]
    assert len(messages) == 1
    assert messages[0].source == "agent-1"
    assert messages[0].target == "agent-2"
    assert messages[0].edge_type == "agent_to_agent"
    assert messages[0].target_kind == "canonical"
    assert graph.nodes["agent-2"].node_type == "agent"


def test_message_log_classifies_mixed_target_kinds(tmp_path):
    """End-to-end: a message log with five recipient shapes produces
    five edges with the expected target_kinds, and the graph nodes
    collapse aliases to canonical agents and broadcasts to `*`."""
    message_log = tmp_path / "messages.jsonl"
    write_jsonl(message_log, [
        {"event": "message", "seq": 0, "from": "agent-1",
         "to": "agent-2", "ts": "2026-05-22T10:00:01.000Z"},
        {"event": "message", "seq": 1, "from": "agent-1",
         "to": "Agent_3", "ts": "2026-05-22T10:00:02.000Z"},
        {"event": "message", "seq": 2, "from": "agent-1",
         "to": "all", "ts": "2026-05-22T10:00:03.000Z"},
        {"event": "message", "seq": 3, "from": "agent-1",
         "to": "parse", "ts": "2026-05-22T10:00:04.000Z"},
        {"event": "message", "seq": 4, "from": "agent-1",
         "to": "orchestrator", "ts": "2026-05-22T10:00:05.000Z"},
    ])
    graph, _ = build_graph(
        "run1", sessions_for(tmp_path), message_log=str(message_log),
        role_names=("parse", "validate", "aggregate", "format_output"))
    messages = [e for e in graph.edges if e.subtype == "message"]
    kinds_by_target = {(m.target, m.target_kind) for m in messages}
    assert kinds_by_target == {
        ("agent-2", "canonical"),
        ("agent-3", "alias"),            # Agent_3 -> agent-3
        ("*", "broadcast"),              # all -> *
        ("parse", "role"),
        ("orchestrator", "unknown"),
    }
    # Graph nodes for the aliased and broadcast targets collapse: there
    # is one node named `agent-3`, not one named `Agent_3`; one node `*`.
    assert "agent-3" in graph.nodes
    assert "Agent_3" not in graph.nodes
    assert "*" in graph.nodes


def test_message_log_n_agent_to_agent_directed_count(tmp_path):
    """The new run-level count records the canonical+alias subset."""
    message_log = tmp_path / "messages.jsonl"
    write_jsonl(message_log, [
        {"event": "message", "from": "agent-1", "to": "agent-2",
         "ts": "2026-05-22T10:00:01.000Z"},
        {"event": "message", "from": "agent-1", "to": "agent3",
         "ts": "2026-05-22T10:00:02.000Z"},
        {"event": "message", "from": "agent-1", "to": "all",
         "ts": "2026-05-22T10:00:03.000Z"},
        {"event": "message", "from": "agent-1", "to": "parse",
         "ts": "2026-05-22T10:00:04.000Z"},
    ])
    graph, _ = build_graph(
        "run1", sessions_for(tmp_path), message_log=str(message_log),
        role_names=("parse",))
    counts = graph.counts()
    assert counts["n_agent_to_agent"] == 4
    # canonical (agent-2) + alias (agent3 -> agent-3) = 2 directed.
    assert counts["n_agent_to_agent_directed"] == 2


def test_message_log_drops_empty_to(tmp_path):
    """Whitespace-only `to` is dropped, matching the historical rule."""
    message_log = tmp_path / "messages.jsonl"
    write_jsonl(message_log, [
        {"event": "message", "from": "agent-1", "to": "",
         "ts": "2026-05-22T10:00:01.000Z"},
        {"event": "message", "from": "agent-1", "to": "   ",
         "ts": "2026-05-22T10:00:02.000Z"},
        {"event": "message", "from": "agent-1", "to": "agent-2",
         "ts": "2026-05-22T10:00:03.000Z"},
    ])
    graph, _ = build_graph("run1", sessions_for(tmp_path),
                           message_log=str(message_log))
    assert sum(1 for e in graph.edges if e.subtype == "message") == 1


# --- CSV datasets ------------------------------------------------------------

def test_parse_run_writes_four_csv_files(tmp_path):
    out_dir = tmp_path / "out"
    parse_run("run1", sessions_for(tmp_path), str(out_dir))
    for name in ("nodes.csv", "edges.csv", "turns.csv", "runs.csv"):
        assert os.path.exists(out_dir / name)


def test_edges_csv_has_expected_columns_and_rows(tmp_path):
    out_dir = tmp_path / "out"
    parse_run("run1", sessions_for(tmp_path), str(out_dir))
    with open(out_dir / "edges.csv", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 3
    assert set(rows[0]) == {
        "run_id", "source", "target", "source_type", "target_type",
        "edge_type", "subtype", "timestamp", "token_cost", "byte_size",
        "turn_uuid", "tool",
        # 2026-05-30 addressing convention: every message edge
        # carries a target_kind; non-message edges (the file edges
        # in this fixture) leave it empty.
        "target_kind",
    }
    assert {r["subtype"] for r in rows} == {"create", "read", "edit"}
    # The file-edge rows in this fixture must have empty target_kind.
    assert all(r["target_kind"] == "" for r in rows)


def test_runs_csv_records_metadata_and_counts(tmp_path):
    out_dir = tmp_path / "out"
    parse_run("run1", sessions_for(tmp_path), str(out_dir),
              run_record={"family": "family-1", "instance": "instance-1",
                          "agent_count": 1, "topology": "solo",
                          "artefact_policy": "allowed", "success": True})
    with open(out_dir / "runs.csv", encoding="utf-8", newline="") as fh:
        row = next(csv.DictReader(fh))
    assert row["run_id"] == "run1"
    assert row["family"] == "family-1"
    assert row["instance"] == "instance-1"
    assert row["completion_time_s"] == "30.0"
    assert row["total_output_tokens"] == "100"
    assert row["n_nodes"] == "3"
    assert row["n_edges"] == "3"
    assert row["n_agent_to_file"] == "2"
    assert row["n_file_to_agent"] == "1"


def test_combine_datasets_concatenates_runs(tmp_path):
    dir_a = tmp_path / "run-a"
    dir_b = tmp_path / "run-b"
    parse_run("run-a", sessions_for(tmp_path), str(dir_a))
    parse_run("run-b", sessions_for(tmp_path), str(dir_b))
    master = tmp_path / "master"
    combine_datasets([str(dir_a), str(dir_b)], str(master))
    with open(master / "edges.csv", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 6
    assert {r["run_id"] for r in rows} == {"run-a", "run-b"}
    with open(master / "runs.csv", encoding="utf-8", newline="") as fh:
        assert len(list(csv.DictReader(fh))) == 2
