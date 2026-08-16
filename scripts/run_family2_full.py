#!/usr/bin/env python3
"""Family 2 full configuration-matrix schedule.

870 runs total. The design is pre-registered on disk at
`memory/experiments/family-2-full/matrix.md` and the analysis plan
at `memory/experiments/family-2-full/analysis-plan.md`. Any change
to the matrix or the analysis plan after the date of those documents
is a deviation from pre-registration and is recorded there with a
reason.

Composition:

  * Main matrix on `summarise_transactions`: the 85-cell non-degenerate
    configuration matrix × the applicable distribution patterns
    × N=10, identical in shape to Family 1's matrix. 850 runs.
  * Baseline cell `(4, peer, allowed, clean)` on `compute_invoices`
    (the 8-step longer chain): N=10. 10 runs.
  * Baseline cell `(4, peer, allowed, clean)` on
    `summarise_transactions_v2` (the non-local CATEGORY_ORDER
    dependency): N=10. 10 runs.

The two extra-task cells share configuration with the main matrix's
baseline summarise_transactions cell, supporting a matched three-way
cross-task comparison at the baseline.

Decisions captured in `memory/decisions.md` (2026-05-30):

  * Mirror Family 1's matrix and N=10 calibration to support the
    cross-family comparison.
  * Keep `compute_invoices` and `summarise_transactions_v2` at one
    baseline cell each at N=10 rather than across the full matrix,
    on the basis that the paper's headline RQs do not require
    scale-dependence proofs for those task variations.
  * Treat n=2 chained as a documented sub-regime; N stays uniform
    at 10. The top-up rule fires on the cell if it triggers.
  * Same model pin (`claude-sonnet-4-6`), same subscription plan,
    same per-run wall-clock ceiling (900 s), same runner cascade
    detector as Family 1.

Runs on the Claude subscription plan; the launcher strips
`ANTHROPIC_API_KEY`. The machine must be signed in to Claude Code
with a Claude subscription. The batch is resumable through the
ledger: an interrupted run is picked up by running the script again.

Usage:

    .venv/bin/python scripts/run_family2_full.py
    .venv/bin/python scripts/run_family2_full.py --reps 10
    .venv/bin/python scripts/run_family2_full.py --reps 10 --start 11  # top-up
    .venv/bin/python scripts/run_family2_full.py --max-runs 100        # daily cap

The --max-runs flag tells the script to do at most N runs in this
invocation and then stop cleanly (master CSVs combined, ledger CSV
written, summary printed). The ledger is durable; the next invocation
without --max-runs resumes from the runs not yet recorded. Use this
to spread the 870-run schedule across multiple subscription windows
at the rate you choose.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_comms.runner import (
    Cell, ClaudeCodeLauncher, ExperimentRunner, expand,
    family_2_main_matrix_specs,
)
from agent_comms.task_generator import get_task


# Baseline cell for the task-variation cells. Cross-references
# memory/experiments/family-2-full/matrix.md.
BASELINE_CELL = Cell(4, "peer", "allowed")
BASELINE_TASKS = ("compute_invoices", "summarise_transactions_v2")
MAIN_TASK = "summarise_transactions"


def build_specs(reps, start):
    """Build the 870-run Family 2 full schedule."""
    specs = []
    # Main matrix on summarise_transactions, 850 runs at N=10.
    if start == 1:
        specs.extend(family_2_main_matrix_specs(
            repetitions=reps, task_id=MAIN_TASK))
    else:
        # Top-up path: expand the main matrix with the given start
        # replication number on every (cell, pattern). The
        # --only-cell-pattern filter for narrower top-ups is left
        # to a follow-up if the analysis plan flags specific cells.
        from agent_comms.runner.matrix import (
            FAMILY_1_PATTERNS, enumerate_cells,
        )
        for cell in enumerate_cells():
            patterns = ("clean",) if cell.agent_count == 1 else FAMILY_1_PATTERNS
            for pattern in patterns:
                specs.extend(expand(
                    [cell], "family-2", MAIN_TASK, pattern,
                    reps, start=start))
    # Baseline cells for the two task-variation tasks, N=10 each.
    if start == 1:
        for task_id in BASELINE_TASKS:
            specs.extend(expand(
                [BASELINE_CELL], "family-2", task_id, "clean", reps))
    return specs


def main():
    parser = argparse.ArgumentParser(
        description="Family 2 full configuration-matrix schedule.")
    parser.add_argument(
        "--experiment-root", default="data/family-2-full",
        help="output directory for the batch (per-run dirs, master, ledger)")
    parser.add_argument("--model", default="claude-sonnet-4-6")
    parser.add_argument("--timeout", type=int, default=900,
                        help="per-run wall-clock ceiling in seconds")
    parser.add_argument("--reps", type=int, default=10,
                        help="repetitions per cell-and-pattern combination")
    parser.add_argument("--start", type=int, default=1,
                        help="first replication number (use 11 for top-up)")
    parser.add_argument("--max-runs", type=int, default=0,
                        help=("at most this many runs in this invocation, "
                              "then stop cleanly (0 = no cap, default). "
                              "Resume on the next invocation picks up from "
                              "the ledger."))
    args = parser.parse_args()

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    specs = build_specs(args.reps, args.start)
    launcher = ClaudeCodeLauncher(model=args.model, timeout_s=args.timeout)
    runner = ExperimentRunner(
        args.experiment_root, launcher, repo_root=repo_root)

    pending = runner.ledger.pending(specs)
    cap_note = (f" (this invocation capped at {args.max_runs})"
                if args.max_runs else "")
    print(f"Family 2 full schedule: {len(specs)} runs planned, "
          f"{len(pending)} pending, model {args.model}, "
          f"start replication {args.start}{cap_note}", flush=True)

    # Specs run mixed tasks (summarise_transactions across the main
    # matrix, compute_invoices and summarise_transactions_v2 at one
    # cell each); the runner's run_all takes a single task argument,
    # so we drive the per-run loop here and resolve the task per spec.
    consecutive_fast_errors = 0
    from agent_comms.runner.runner import (
        RATE_LIMIT_CONSECUTIVE_THRESHOLD, RATE_LIMIT_FAST_ERROR_S,
    )
    from agent_comms.runner.model import STATUS_ERROR

    n_pending = len(pending)
    completed_this_session = 0
    for i, spec in enumerate(pending, 1):
        if args.max_runs and completed_this_session >= args.max_runs:
            print(f"\nSTOPPING: --max-runs cap reached "
                  f"({args.max_runs} completed this invocation). "
                  f"Re-run the script to resume from the ledger.\n",
                  flush=True)
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

        # Cascade detection, same shape as runner.run_all.
        if (result.status == STATUS_ERROR
                and result.wall_time_s < RATE_LIMIT_FAST_ERROR_S):
            consecutive_fast_errors += 1
            if consecutive_fast_errors >= RATE_LIMIT_CONSECUTIVE_THRESHOLD:
                msg = (
                    f"\nPAUSING BATCH: {consecutive_fast_errors} consecutive "
                    f"runs errored in under {RATE_LIMIT_FAST_ERROR_S:.0f}s. "
                    f"Rate-limit cascade signature. Re-run when the "
                    f"subscription window resets; the ledger resumes from "
                    f"the errored runs.\n")
                print(msg, flush=True)
                break
        else:
            consecutive_fast_errors = 0

        # Periodic combine every 25 runs.
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
