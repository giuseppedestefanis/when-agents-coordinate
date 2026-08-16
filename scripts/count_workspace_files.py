#!/usr/bin/env python3
"""End-of-run workspace file counts.

This is the one statistic in the paper that is NOT read from the committed
master CSV files: it is a listing of the retained per-run ``workspace/``
directories (released alongside the CSVs). It counts how many files each run
left in its workspace at end of run, as opposed to the in-run
``n_file_nodes`` touched-path count that lives in ``runs.csv``.

Counting rule (the released definition)
---------------------------------------
COUNT = the number of regular files under ``<run>/workspace/``, searched
recursively, with exactly one exclusion:

  * Python bytecode caches are excluded: any directory named ``__pycache__``
    and any ``*.pyc`` file. These are created by the verifier when it imports
    the agents' ``solution.py`` AFTER the agents have finished; they are
    harness/post-hoc artefacts, not agent output.

Everything else counts: ``solution.py`` (the required deliverable) and every
other file the agents wrote, including files placed inside subdirectories
(each counted once). Directories themselves are not counted as items, only the
regular files within them. Hidden/dotfiles are included if present (they would
be agent output); none occur in the released data.

Why recursive-files-excluding-bytecode and not "top-level entries". Agents
occasionally nest a spec file in a subdirectory; a recursive file count counts
that file once, wherever it sits. Counting top-level directory entries instead
(treating a subdirectory as a single item) both miscounts a multi-file
subdirectory as one and counts an empty scratch directory as a file; counting
top-level files only silently drops the nested files. The recursive regular-
file count is the estimator that answers "how many files did the agents
leave", which is what the policy comparison in 4.1 reports.

Usage
-----
    .venv/bin/python scripts/count_workspace_files.py \
        --experiment-root data/family-1-full \
        --csv data/family-1-full/master/workspace_counts.csv

Prints the per-cell means the paper reports (forbidden n=8 peer over the three
patterns; mandatory n=8 over the three topologies and three patterns) and,
with --csv, writes one row per run.
"""

from __future__ import annotations

import argparse
import csv
import glob
import os
import re
import statistics
import sys

# Reuses the Family-1 / Family-2 run-id grammar. agent_count, topology and
# artefact_policy are parsed from the directory name so the script needs only
# the workspace listing, never the CSVs.
RUN_RE = re.compile(
    r"^family-(?P<family>\d+)-(?P<task>[a-z_0-9]+)"
    r"-(?P<pattern>clean|overlapping|conflicting)"
    r"-a(?P<agents>\d+)-(?P<topology>solo|peer|orchestrator)"
    r"-(?P<policy>forbidden|allowed|mandatory)-r(?P<rep>\d+)$")


def count_workspace_files(workspace_dir):
    """Regular files under workspace_dir, recursive, excluding __pycache__/
    directories and *.pyc bytecode. Returns None if there is no workspace."""
    if not os.path.isdir(workspace_dir):
        return None
    n = 0
    for root, dirs, files in os.walk(workspace_dir):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            if f.endswith(".pyc"):
                continue
            n += 1
    return n


def parse_run_id(run_id):
    m = RUN_RE.match(run_id)
    if not m:
        return None
    return {
        "run_id": run_id,
        "agent_count": int(m["agents"]),
        "topology": m["topology"],
        "artefact_policy": m["policy"],
        "pattern": m["pattern"],
        "task": m["task"],
    }


def collect(experiment_root):
    rows = []
    runs_root = os.path.join(experiment_root, "runs")
    for run_dir in sorted(glob.glob(os.path.join(runs_root, "*"))):
        run_id = os.path.basename(run_dir)
        parts = parse_run_id(run_id)
        if parts is None:
            continue
        count = count_workspace_files(os.path.join(run_dir, "workspace"))
        if count is None:
            continue
        parts["workspace_file_count"] = count
        rows.append(parts)
    return rows


def cell_mean(rows, **filters):
    sel = [r["workspace_file_count"] for r in rows
           if all(r.get(k) == v for k, v in filters.items())]
    return (statistics.fmean(sel) if sel else float("nan")), len(sel)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--experiment-root", default="data/family-1-full")
    ap.add_argument("--csv", default=None,
                    help="optional: write one row per run here")
    args = ap.parse_args()

    rows = collect(args.experiment_root)
    if not rows:
        print(f"no parseable runs with workspaces under {args.experiment_root}")
        sys.exit(0)

    if args.csv:
        os.makedirs(os.path.dirname(args.csv) or ".", exist_ok=True)
        with open(args.csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=[
                "run_id", "agent_count", "topology", "artefact_policy",
                "pattern", "task", "workspace_file_count"])
            w.writeheader()
            for r in rows:
                w.writerow(r)
        print(f"wrote {args.csv} ({len(rows)} runs)")

    # The two cells the paper reports in 4.1.
    m1, n1 = cell_mean(rows, agent_count=8, topology="peer",
                       artefact_policy="forbidden")
    print(f"forbidden, n=8 peer (pooled over patterns): "
          f"mean={m1:.4f}  N={n1}")
    m2, n2 = cell_mean(rows, agent_count=8, artefact_policy="mandatory")
    print(f"mandatory, n=8 (pooled over topologies and patterns): "
          f"mean={m2:.4f}  N={n2}")


if __name__ == "__main__":
    main()
