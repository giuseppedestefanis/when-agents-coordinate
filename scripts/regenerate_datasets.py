#!/usr/bin/env python3
"""Regenerate the per-run and master CSV datasets for an experiment.

Reparses every run under <experiment_root>/runs/ using the current
parser, then rebuilds <experiment_root>/master/*.csv via
combine_datasets. The session JSONL files and the message protocol
log on disk are the inputs; the new parser convention (target_kind
column, n_agent_to_agent_directed column, canonicalised addressing)
takes effect on the regenerated CSVs.

The script is idempotent: rerunning it on already-regenerated data
produces identical output.

The run_record metadata for each run is read from its existing
datasets/runs.csv so the regeneration preserves family, instance,
agent_count, topology, artefact_policy and success. The role_names
needed for the new target-kind classification are looked up from
the task generator library by task_id derived from the run_id.

Usage:

    .venv/bin/python scripts/regenerate_datasets.py \\
        --experiment-root data/family-1-full

    .venv/bin/python scripts/regenerate_datasets.py \\
        --experiment-root data/family-2-pilot
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_comms.parser import combine_datasets, parse_run
from agent_comms.task_generator import get_task
from agent_comms.task_generator.library import role_names_for


# The runner's run_id format is:
#   <family>-<task_id>-<pattern>-a<n>-<topology>-<policy>-r<rep>
# Family 1 task_id is `process_orders`. Family 2 task_ids include
# `summarise_transactions`, `compute_invoices`,
# `summarise_transactions_v2`. The regex pulls task_id verbatim.
_RUN_ID_RE = re.compile(
    r"^(?P<family>family-[12])-(?P<task>[a-z_0-9]+)"
    r"-(?P<pattern>clean|overlapping|conflicting)"
    r"-a(?P<agents>\d+)-(?P<topology>solo|peer|orchestrator)"
    r"-(?P<policy>forbidden|allowed|mandatory)-r(?P<rep>\d+)$"
)


def _existing_run_record(run_dir):
    """Read the per-run datasets/runs.csv to recover run-record metadata.

    Returns a dict with at least family / instance / agent_count /
    topology / artefact_policy / success when the file exists, or
    None if the file is absent (the runner never wrote it for an
    errored run that the parser skipped).
    """
    runs_csv = os.path.join(run_dir, "datasets", "runs.csv")
    if not os.path.exists(runs_csv):
        return None
    with open(runs_csv) as fh:
        for row in csv.DictReader(fh):
            return {
                "family": row.get("family", ""),
                "instance": row.get("instance", ""),
                "agent_count": int(row.get("agent_count", 0) or 0),
                "topology": row.get("topology", ""),
                "artefact_policy": row.get("artefact_policy", ""),
                "success": (row.get("success", "False").lower() == "true"),
            }
    return None


def _task_for_run(run_id):
    """Look up the Task object for a run_id, for role_names_for()."""
    m = _RUN_ID_RE.match(run_id)
    if not m:
        return None
    try:
        return get_task(m["task"])
    except KeyError:
        return None


def _sessions_for(run_dir):
    sessions = []
    sessions_dir = os.path.join(run_dir, "sessions")
    if not os.path.isdir(sessions_dir):
        return sessions
    for name in sorted(os.listdir(sessions_dir)):
        if not name.endswith(".jsonl"):
            continue
        sessions.append({
            "agent_id": name[:-len(".jsonl")],
            "path": os.path.join(sessions_dir, name),
        })
    return sessions


def regenerate(experiment_root, verbose=True):
    runs_root = os.path.join(experiment_root, "runs")
    if not os.path.isdir(runs_root):
        print(f"no runs/ under {experiment_root}", file=sys.stderr)
        return 0
    master_dir = os.path.join(experiment_root, "master")

    run_dirs = sorted(
        d for d in (os.path.join(runs_root, n) for n in os.listdir(runs_root))
        if os.path.isdir(d)
    )
    n_total = len(run_dirs)
    if verbose:
        print(f"reparsing {n_total} runs under {runs_root}", flush=True)

    t0 = time.perf_counter()
    n_done = 0
    skipped = []
    for run_dir in run_dirs:
        run_id = os.path.basename(run_dir)
        record = _existing_run_record(run_dir)
        sessions = _sessions_for(run_dir)
        if record is None or not sessions:
            skipped.append((run_id,
                            "no runs.csv" if record is None
                            else "no sessions"))
            continue
        task = _task_for_run(run_id)
        record["role_names"] = role_names_for(task) if task else []
        message_log = os.path.join(run_dir, "messages.jsonl")
        if not os.path.exists(message_log):
            message_log = None
        out_dir = os.path.join(run_dir, "datasets")
        parse_run(run_id, sessions, out_dir,
                  message_log=message_log, run_record=record)
        n_done += 1
        if verbose and n_done % 100 == 0:
            elapsed = time.perf_counter() - t0
            rate = n_done / elapsed if elapsed > 0 else 0.0
            print(f"  {n_done}/{n_total} reparsed in {elapsed:.1f}s "
                  f"({rate:.1f} runs/s)", flush=True)

    elapsed = time.perf_counter() - t0
    if verbose:
        print(f"reparsed {n_done} runs in {elapsed:.1f}s "
              f"({n_done/elapsed:.1f} runs/s)", flush=True)
        if skipped:
            print(f"skipped {len(skipped)} run dirs:", flush=True)
            for run_id, reason in skipped[:5]:
                print(f"  {run_id}: {reason}", flush=True)
            if len(skipped) > 5:
                print(f"  ... and {len(skipped) - 5} more", flush=True)

    if verbose:
        print(f"combining into master at {master_dir}", flush=True)
    combine_datasets(
        [os.path.join(d, "datasets") for d in run_dirs
         if os.path.isdir(os.path.join(d, "datasets"))],
        master_dir,
    )
    if verbose:
        print("done.", flush=True)
    return n_done


def main():
    parser = argparse.ArgumentParser(
        description="Regenerate per-run and master CSV datasets.")
    parser.add_argument("--experiment-root", required=True,
                        help="path to data/<experiment>/ root")
    parser.add_argument("--quiet", action="store_true",
                        help="suppress progress output")
    args = parser.parse_args()
    regenerate(args.experiment_root, verbose=not args.quiet)


if __name__ == "__main__":
    main()
