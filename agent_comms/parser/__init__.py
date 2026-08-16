"""Session parser (infrastructure component 2).

Ingests Claude Code session JSONL files, builds the heterogeneous temporal
graph for a run (agent and file nodes, typed timestamped weighted edges, as
defined in PLAN.md), and writes the graph out as CSV datasets for downstream
network analysis.

Public entry point: parse_run.

Modules:
- model: the graph data model (Node, Edge, Turn, RunGraph).
- sessions: extraction of turns and tool calls from one session JSONL file.
- build: construction of a RunGraph from session files and the message log.
- datasets: writing the graph to CSV datasets, and combining runs.
"""

from agent_comms.parser.build import build_graph
from agent_comms.parser.datasets import combine_datasets, write_datasets
from agent_comms.parser.model import Edge, Node, RunGraph, Turn

__all__ = [
    "parse_run", "build_graph", "write_datasets", "combine_datasets",
    "Edge", "Node", "RunGraph", "Turn",
]


def parse_run(run_id, sessions, out_dir, message_log=None, run_record=None):
    """Parse one run and write its CSV datasets.

    run_id: identifier for the run.
    sessions: list of {"agent_id": str, "path": str}, one per session JSONL
        file in the run.
    out_dir: directory to write nodes.csv, edges.csv, turns.csv and runs.csv.
    message_log: optional path to the message protocol JSONL log for the run.
    run_record: optional dict of run metadata (family, instance, agent_count,
        topology, artefact_policy, success) recorded in runs.csv.
        May include `role_names`, the list of addressable role names for
        this run's task; the parser uses it to classify message recipients
        as TARGET_KIND_ROLE rather than TARGET_KIND_UNKNOWN. Family 1 runs
        ship with an empty role_names; Family 2 runs ship with their step
        names (excluding the unowned `pipeline` slot).

    Returns (graph, turns).
    """
    record = dict(run_record or {})
    record["run_id"] = run_id
    role_names = tuple(record.get("role_names") or ())
    graph, turns = build_graph(
        run_id, sessions, message_log, role_names=role_names)
    write_datasets(graph, turns, record, out_dir)
    return graph, turns
