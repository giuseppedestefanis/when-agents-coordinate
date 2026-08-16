#!/usr/bin/env python3
"""Re-validation of the int-vs-float specification tightening.

The Family 1 broader pilot showed that 9 of 10 verifier failures hit the same
single assertion: `isinstance(result["total"], float)`. The cause was Python
type-pedantry: when discounts did not change the amount and inputs were
integers, the sum stayed an `int` and `round(int, 2)` returned an `int`, so
the summary's `total` was reported as an `int` rather than a `float`. The
verifier is strict by design; on 2026-05-23 Component A in
`agent_comms/task_generator/library.py` (and the corresponding markdown
design documents) was tightened to state explicitly that `total` is always
returned as a float, including when its value is a whole number.

This script re-runs the cell where the original failure rate was highest
(`clean / 4 agents / orchestrator / forbidden`, which missed the subtlety
in two of its three pilot runs) three more times with the tightened spec.
If the failure rate drops, the spec fix is confirmed and the full schedule
has a cleaner outcome variable on this assertion.

Three runs only. Like the other scripts in this folder it runs on the
Claude subscription plan (the launcher strips `ANTHROPIC_API_KEY`); the
machine must be signed in to Claude Code with a subscription. Resumable
through the ledger.

Usage:

    .venv/bin/python scripts/run_spec_check.py

After the runs complete, compare the verifier outcomes against the pilot
cell of the same name in
`data/family-1-pilot/runs/family-1-process_orders-clean-a4-orchestrator-forbidden-r0[1-3]`.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_comms.runner import (
    Cell, ClaudeCodeLauncher, ExperimentRunner, expand,
)
from agent_comms.task_generator import get_task


def main():
    parser = argparse.ArgumentParser(
        description="Spec-fix re-validation on the worst-affected pilot cell.")
    parser.add_argument(
        "--experiment-root", default="data/family-1-spec-check")
    parser.add_argument("--model", default="claude-sonnet-4-6",
                        help="model identifier pinned for every agent")
    parser.add_argument("--timeout", type=int, default=900,
                        help="per-run wall-clock ceiling in seconds")
    parser.add_argument("--reps", type=int, default=3)
    args = parser.parse_args()

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cell = Cell(4, "orchestrator", "forbidden")
    specs = expand(
        [cell], "family-1", "process_orders", "clean", args.reps)
    task = get_task("process_orders")
    launcher = ClaudeCodeLauncher(model=args.model, timeout_s=args.timeout)
    runner = ExperimentRunner(
        args.experiment_root, launcher, repo_root=repo_root)

    pending = runner.ledger.pending(specs)
    print(f"spec-fix re-validation: {len(specs)} runs, "
          f"{len(pending)} pending, model {args.model}", flush=True)
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
