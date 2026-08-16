#!/usr/bin/env python3
"""compute_invoices scaling arm — H7 pre-registered batch.

30 fresh runs: compute_invoices, peer/allowed/clean, n ∈ {2, 4, 8}, N=10/cell.

Design and scientific rationale: memory/experiments/compute-invoices-scaling/design.md
Pre-commitment commit: dfad8a0 (paper: H7 pre-commitment + review-response prose updates)

Do NOT merge or compare these runs with the 10 existing n=4 runs in
data/family-2-full/master/ — those are a separate batch and serve only as a
cross-batch stability check (Mann-Whitney old vs new n=4). The H7 piecewise
log-log regression uses only the 30 runs collected here.

Usage:

    .venv/bin/python scripts/run_compute_invoices_scaling.py
    .venv/bin/python scripts/run_compute_invoices_scaling.py --max-runs 10

Launched via guardian wrapper:

    .venv/bin/python scripts/run_with_guardian.py \\
        --log data/compute-invoices-scaling-run.log \\
        --per-run-timeout 1000 \\
        -- /usr/bin/env -u ANTHROPIC_API_KEY \\
           .venv/bin/python scripts/run_compute_invoices_scaling.py --max-runs N
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_comms.runner import (
    Cell, ClaudeCodeLauncher, ExperimentRunner, expand,
)
from agent_comms.runner.runner import (
    RATE_LIMIT_CONSECUTIVE_THRESHOLD, RATE_LIMIT_FAST_ERROR_S,
)
from agent_comms.runner.model import STATUS_ERROR
from agent_comms.task_generator import get_task

TASK_ID = "compute_invoices"
FAMILY = "family-2"
PATTERN = "clean"
TOPOLOGY = "peer"
POLICY = "allowed"
REPS = 10

# Three cells: n=2, n=4, n=8 at peer/allowed.
SCALING_CELLS = [Cell(n, TOPOLOGY, POLICY) for n in (2, 4, 8)]


def build_specs(reps=REPS):
    """30 fresh runs: n∈{2,4,8} × N=10, all in one batch."""
    return expand(SCALING_CELLS, FAMILY, TASK_ID, PATTERN, reps)


def main():
    parser = argparse.ArgumentParser(
        description="compute_invoices H7 scaling arm (30 fresh runs).")
    parser.add_argument(
        "--experiment-root", default="data/compute-invoices-scaling",
        help="output directory for the batch")
    parser.add_argument("--model", default="claude-sonnet-4-6")
    parser.add_argument("--timeout", type=int, default=900,
                        help="per-run wall-clock ceiling in seconds")
    parser.add_argument("--max-runs", type=int, default=0,
                        help=("at most this many runs this invocation, "
                              "then stop cleanly (0 = no cap). "
                              "Resume picks up from the ledger."))
    args = parser.parse_args()

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    specs = build_specs()
    launcher = ClaudeCodeLauncher(model=args.model, timeout_s=args.timeout)
    runner = ExperimentRunner(
        args.experiment_root, launcher, repo_root=repo_root)

    pending = runner.ledger.pending(specs)
    cap_note = (f" (this invocation capped at {args.max_runs})"
                if args.max_runs else "")
    print(f"H7 compute_invoices scaling arm: {len(specs)} runs planned, "
          f"{len(pending)} pending, model {args.model}{cap_note}", flush=True)

    consecutive_fast_errors = 0
    n_pending = len(pending)
    completed_this_session = 0

    for i, spec in enumerate(pending, 1):
        if args.max_runs and completed_this_session >= args.max_runs:
            print(f"\nSTOPPING: --max-runs cap reached "
                  f"({args.max_runs} completed this invocation). "
                  f"Re-run to resume from the ledger.\n", flush=True)
            break
        print(f"[{i}/{n_pending}] {spec.run_id}", flush=True)
        task = get_task(spec.task_id)
        result = runner.run_one(spec, task)
        completed_this_session += 1
        print(f"    status={result.status} success={result.success} "
              f"passed={result.tests_passed} failed={result.tests_failed} "
              f"wall={result.wall_time_s}s", flush=True)
        if result.error:
            print(f"    error: {result.error}", flush=True)

        if (result.status == STATUS_ERROR
                and result.wall_time_s < RATE_LIMIT_FAST_ERROR_S):
            consecutive_fast_errors += 1
            if consecutive_fast_errors >= RATE_LIMIT_CONSECUTIVE_THRESHOLD:
                msg = (
                    f"\nPAUSING BATCH: {consecutive_fast_errors} consecutive "
                    f"runs errored in under {RATE_LIMIT_FAST_ERROR_S:.0f}s. "
                    f"Rate-limit cascade signature. Re-run when the "
                    f"subscription window resets.\n")
                print(msg, flush=True)
                break
        else:
            consecutive_fast_errors = 0

        if i % 25 == 0:
            try:
                runner.combine()
            except Exception as exc:
                print(f"    (combine warning: {exc})", flush=True)

    runner.combine()
    runner.ledger.write_csv(
        os.path.join(runner.experiment_root, "ledger.csv"))
    print(f"done. completed this invocation: {completed_this_session}. "
          f"summary: {runner.ledger.summary()}", flush=True)
    print(f"master datasets: {runner.master_dir}", flush=True)


if __name__ == "__main__":
    main()
