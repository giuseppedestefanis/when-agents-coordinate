#!/usr/bin/env python3
"""Compare the forbidden-policy regimes: instruction-based vs tool-restricted.

The broader pilot ran the instruction-based forbidden regime
(`data/family-1-pilot/`). The ablation
(`data/family-1-ablation/`) ran the same cell (4 agents, peer topology,
clean distribution, `forbidden` policy) with the workspace directory locked at
the filesystem level. This script loads both, prints a side-by-side summary of
graph counts, and lists the surviving workspace contents.

Usage:

    .venv/bin/python scripts/analyse_ablation.py
"""

import argparse
import csv
import os
import sys
from statistics import mean

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load_forbidden_rows(experiment_root):
    """Return the runs.csv rows for the peer/4-agent/forbidden/clean cell."""
    path = os.path.join(experiment_root, "master", "runs.csv")
    with open(path, "r", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    matched = []
    for r in rows:
        if (r["topology"] == "peer" and r["artefact_policy"] == "forbidden"
                and int(r["agent_count"]) == 4
                and r["instance"].endswith("/clean")):
            matched.append(r)
    return matched


def _summarise(rows, label):
    a2a = [int(r["n_agent_to_agent"]) for r in rows]
    a2f = [int(r["n_agent_to_file"]) for r in rows]
    f2a = [int(r["n_file_to_agent"]) for r in rows]
    file_nodes = [int(r["n_file_nodes"]) for r in rows]
    print(f"\n{label} ({len(rows)} runs)")
    print(f"  {'run_id':<60}{'succ':>6}{'a2a':>5}{'a2f':>5}{'f2a':>5}"
          f"{'file_nodes':>12}")
    for r in rows:
        print(f"  {r['run_id']:<60}{r['success']:>6}"
              f"{r['n_agent_to_agent']:>5}{r['n_agent_to_file']:>5}"
              f"{r['n_file_to_agent']:>5}{r['n_file_nodes']:>12}")
    print(f"  {'mean':<60}{'':>6}{mean(a2a):>5.1f}{mean(a2f):>5.1f}"
          f"{mean(f2a):>5.1f}{mean(file_nodes):>12.1f}")
    success = sum(r["success"] == "True" for r in rows)
    print(f"  verifier success: {success}/{len(rows)}")


def _list_workspaces(experiment_root, label):
    runs_dir = os.path.join(experiment_root, "runs")
    if not os.path.isdir(runs_dir):
        return
    print(f"\n{label} workspaces (files remaining after the run):")
    for run in sorted(os.listdir(runs_dir)):
        ws = os.path.join(runs_dir, run, "workspace")
        if not os.path.isdir(ws):
            continue
        files = [name for name in sorted(os.listdir(ws))
                 if not name.startswith("__")]
        sizes = []
        for name in files:
            try:
                sizes.append(f"{name} ({os.path.getsize(os.path.join(ws, name))}B)")
            except OSError:
                sizes.append(name)
        print(f"  {run}")
        print(f"    {', '.join(sizes) if sizes else '(empty)'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot-root", default="data/family-1-pilot")
    parser.add_argument("--ablation-root", default="data/family-1-ablation")
    args = parser.parse_args()

    pilot = _load_forbidden_rows(args.pilot_root)
    ablation = _load_forbidden_rows(args.ablation_root)
    _summarise(pilot, "Instruction-based forbidden (pilot)")
    _summarise(ablation, "Tool-restricted forbidden (ablation)")
    _list_workspaces(args.pilot_root, "Instruction-based")
    _list_workspaces(args.ablation_root, "Tool-restricted")


if __name__ == "__main__":
    main()
