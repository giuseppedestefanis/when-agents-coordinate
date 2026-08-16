#!/usr/bin/env python3
"""Run the artefact-policy enforcement ablation.

The broader pilot showed that the forbidden artefact policy leaks when it is
communicated by prompt only: agents still create coordination files despite
the prompt clause saying the deliverable is the only file they may create.
This ablation tests whether enforcing the policy at the filesystem level (the
workspace directory is locked read-only except for the pre-created
solution.py) produces a meaningfully different communication graph from the
instruction-based regime.

The cell mirrors the pilot's most-discussed forbidden cell: four agents, peer
topology, clean distribution. The ablation runs 3 repetitions under the
tool-restricted forbidden regime; the 3 instruction-based runs to compare
against are already in:

  data/family-1-pilot/runs/family-1-process_orders-clean-a4-peer-forbidden-r0[1-3]

This invokes the real `claude` command line on the Claude subscription plan.
Output: data/family-1-ablation/. Resumable through the ledger.

Usage:

    .venv/bin/python scripts/run_ablation.py
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_comms.runner import (
    Cell, ClaudeCodeLauncher, ExperimentRunner, expand,
    lock_workspace_for_strict_forbidden,
)
from agent_comms.task_generator import get_task


def main():
    parser = argparse.ArgumentParser(
        description="Forbidden-policy enforcement ablation.")
    parser.add_argument("--experiment-root", default="data/family-1-ablation")
    parser.add_argument("--model", default="claude-sonnet-4-6",
                        help="model identifier pinned for every agent")
    parser.add_argument("--timeout", type=int, default=900,
                        help="per-run wall-clock ceiling in seconds")
    parser.add_argument("--reps", type=int, default=3,
                        help="repetitions of the tool-restricted forbidden cell")
    args = parser.parse_args()

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cell = Cell(4, "peer", "forbidden")
    specs = expand([cell], "family-1", "process_orders", "clean", args.reps)
    task = get_task("process_orders")
    launcher = ClaudeCodeLauncher(model=args.model, timeout_s=args.timeout)

    # The hook locks the workspace after prepare_run, before the launcher
    # starts the agents. This is the only difference from the pilot.
    runner = ExperimentRunner(
        args.experiment_root, launcher, repo_root=repo_root,
        post_prepare=lock_workspace_for_strict_forbidden)

    pending = runner.ledger.pending(specs)
    print(f"forbidden enforcement ablation: {len(specs)} runs, "
          f"{len(pending)} pending, model {args.model}, "
          f"tool-restricted (workspace locked at the filesystem level)",
          flush=True)
    for i, spec in enumerate(pending, 1):
        print(f"[{i}/{len(pending)}] {spec.run_id}", flush=True)
        result = runner.run_one(spec, task)
        print(f"    status={result.status} success={result.success} "
              f"passed={result.tests_passed} failed={result.tests_failed} "
              f"wall={result.wall_time_s}s", flush=True)
        if result.error:
            print(f"    error: {result.error}", flush=True)

    runner.combine()
    runner.ledger.write_csv(
        os.path.join(runner.experiment_root, "ledger.csv"))
    print(f"done. summary: {runner.ledger.summary()}", flush=True)
    print(f"master datasets: {runner.master_dir}", flush=True)


if __name__ == "__main__":
    main()
