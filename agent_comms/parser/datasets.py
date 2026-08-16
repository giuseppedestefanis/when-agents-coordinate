"""Writing the run graph to CSV datasets, and combining runs.

Four CSV files per run, written to one directory:

- nodes.csv: one row per node (agent or file).
- edges.csv: one row per edge. This is the analysable core; it loads directly
  into networkx (from_pandas_edgelist) or Gephi to build the network. The
  `target_kind` column on a message edge classifies the recipient as one of
  {canonical, alias, broadcast, role, unknown}; for non-message edges
  (agent-to-file, file-to-agent) the column is empty.
- turns.csv: one row per model turn, with authoritative token usage. Edges
  carry a turn_uuid that joins to this table for token analysis.
- runs.csv: one row, the run-level record with configuration and outcome
  fields and summary network counts, for cross-run analysis. Both the total
  agent-to-agent event count (`n_agent_to_agent`) and the directed subset
  (`n_agent_to_agent_directed`, messages whose target_kind is canonical or
  alias) are recorded.

combine_datasets concatenates the per-run files of many runs into one master
set of CSVs, so an analysis can load every run at once.
"""

from __future__ import annotations

import csv
import os
from datetime import datetime

NODE_FIELDS = ["run_id", "node_id", "node_type", "label"]

EDGE_FIELDS = [
    "run_id", "source", "target", "source_type", "target_type", "edge_type",
    "subtype", "timestamp", "token_cost", "byte_size", "turn_uuid", "tool",
    "target_kind",
]

TURN_FIELDS = [
    "run_id", "agent", "turn_uuid", "timestamp", "is_sidechain",
    "input_tokens", "output_tokens", "cache_read_tokens",
    "cache_creation_tokens", "model",
]

RUN_FIELDS = [
    "run_id", "family", "instance", "agent_count", "topology",
    "artefact_policy", "success", "completion_time_s", "total_input_tokens",
    "total_output_tokens", "n_nodes", "n_edges", "n_agent_nodes",
    "n_file_nodes", "n_agent_to_agent", "n_agent_to_agent_directed",
    "n_agent_to_file", "n_file_to_agent",
]

_DATASETS = {
    "nodes.csv": NODE_FIELDS,
    "edges.csv": EDGE_FIELDS,
    "turns.csv": TURN_FIELDS,
    "runs.csv": RUN_FIELDS,
}


def _parse_ts(value):
    """Parse an ISO 8601 timestamp, tolerating a trailing Z. Return or None."""
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _completion_time(turns) -> float:
    """Return the wall-clock span of a run in seconds, from turn timestamps."""
    stamps = [t for t in (_parse_ts(turn.timestamp) for turn in turns)
              if t is not None]
    if len(stamps) < 2:
        return 0.0
    return round((max(stamps) - min(stamps)).total_seconds(), 3)


def _run_row(graph, turns, run_record) -> dict:
    row = {field: run_record.get(field, "") for field in RUN_FIELDS}
    row["run_id"] = run_record.get("run_id", graph.run_id)
    row["completion_time_s"] = _completion_time(turns)
    row["total_input_tokens"] = sum(t.input_tokens for t in turns)
    row["total_output_tokens"] = sum(t.output_tokens for t in turns)
    row.update(graph.counts())
    return row


def _write_csv(path, fields, rows) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_datasets(graph, turns, run_record, out_dir) -> dict:
    """Write nodes.csv, edges.csv, turns.csv and runs.csv into out_dir.

    Returns a dict of the written file paths.
    """
    os.makedirs(out_dir, exist_ok=True)
    node_rows = [
        {"run_id": n.run_id, "node_id": n.node_id, "node_type": n.node_type,
         "label": n.label}
        for n in graph.nodes.values()
    ]
    edge_rows = [vars(e) for e in graph.edges]
    turn_rows = [vars(t) for t in turns]
    run_rows = [_run_row(graph, turns, run_record)]

    paths = {}
    for name, rows in (("nodes.csv", node_rows), ("edges.csv", edge_rows),
                       ("turns.csv", turn_rows), ("runs.csv", run_rows)):
        path = os.path.join(out_dir, name)
        _write_csv(path, _DATASETS[name], rows)
        paths[name] = path
    return paths


def combine_datasets(run_dirs, master_dir) -> dict:
    """Concatenate the per-run CSV datasets of many runs into master_dir.

    run_dirs: iterable of directories, each holding one run's CSV datasets.
    Returns a dict of the written master file paths.
    """
    os.makedirs(master_dir, exist_ok=True)
    paths = {}
    for name, fields in _DATASETS.items():
        rows = []
        for run_dir in run_dirs:
            source = os.path.join(run_dir, name)
            if not os.path.exists(source):
                continue
            with open(source, "r", encoding="utf-8", newline="") as fh:
                rows.extend(csv.DictReader(fh))
        path = os.path.join(master_dir, name)
        _write_csv(path, fields, rows)
        paths[name] = path
    return paths
