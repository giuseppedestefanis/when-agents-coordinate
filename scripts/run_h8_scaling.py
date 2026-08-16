#!/usr/bin/env python3
"""H8 16-agent scaling arm — pre-registered batch.

70 fresh runs of `process_billing` (Family 2, Instance 6, sixteen-step chain):
  - break test:  peer/allowed/clean, n in {4, 8, 16}, N=20/cell = 60 runs.
  - linearisation check: peer/mandatory/clean, n=16, N=10 = 10 runs.

Design and pre-registration: memory/experiments/h8-16agent/design.md
(the analysis plan + decision rule are committed BEFORE any run; the commit
timestamp is the proof of pre-registration).

INTERLEAVED ORDER (important): the specs are emitted round-robin across the
cells, one repetition at a time, NOT cell-by-cell. A scaling-slope arm must not
confound agent count with collection session/time -- collecting all of one n in
one sitting and another n in a later sitting would bias the segment slopes
(the paper's own finding is that the Family-1 exponent swings 1.76-2.44 between
sessions). With the round-robin order any prefix of runs is balanced across the
cells to within one run, so incremental collection (--max-runs in batches) stays
unbiased. Single uninterrupted batch is still ideal; short rate-limit pauses are
free, multi-day gaps add cross-session variance (record it).

Model pinned to claude-sonnet-4-6 (every prior batch used it; cross-cell
comparison requires a fixed model), recorded per turn in turns.csv. Own ledger
and master under data/h8-16agent/ so cross-batch analysis is one concatenation.
Do NOT mix these runs with any other batch on the segment endpoints.

Usage:

    .venv/bin/python scripts/run_h8_scaling.py
    .venv/bin/python scripts/run_h8_scaling.py --max-runs 12   # one increment

Launched via the guardian wrapper (n=16 is the heaviest cell; raise the
per-run timeout above the launcher ceiling):

    .venv/bin/python scripts/run_with_guardian.py \\
        --log data/h8-16agent-run.log \\
        --per-run-timeout 2000 \\
        -- /usr/bin/env -u ANTHROPIC_API_KEY \\
           .venv/bin/python scripts/run_h8_scaling.py --max-runs N
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

FAMILY = "family-2"          # process_billing is a Family-2 chain task
TASK_ID = "process_billing"
PATTERN = "clean"
TOPOLOGY = "peer"
BREAK_N = (4, 8, 16)         # the piecewise-slope cells (knot at n=8)
BREAK_REPS = 20              # N=20 (H7 at N=10 was power-limited)
MANDATORY_N = 16             # the channel-linearisation check
MANDATORY_REPS = 10


def build_specs():
    """70 specs, INTERLEAVED round-robin so any prefix is cell-balanced.

    Each round r emits one rep of n=4, n=8, n=16 (allowed); for the first
    MANDATORY_REPS rounds it also emits one rep of the n=16 mandatory cell, so
    the mandatory runs are interleaved with (not collected after) the n=16
    allowed runs they are compared against.
    """
    allowed = [Cell(n, TOPOLOGY, "allowed") for n in BREAK_N]
    mandatory = Cell(MANDATORY_N, TOPOLOGY, "mandatory")
    specs = []
    for rep in range(1, BREAK_REPS + 1):
        for cell in allowed:
            specs.append(
                expand([cell], FAMILY, TASK_ID, PATTERN, 1, start=rep)[0])
        if rep <= MANDATORY_REPS:
            specs.append(
                expand([mandatory], FAMILY, TASK_ID, PATTERN, 1, start=rep)[0])
    return specs


def main():
    parser = argparse.ArgumentParser(
        description="H8 16-agent scaling arm (70 fresh runs).")
    parser.add_argument(
        "--experiment-root", default="data/h8-16agent",
        help="output directory for the batch")
    parser.add_argument("--model", default="claude-sonnet-4-6")
    parser.add_argument(
        "--timeout", type=int, default=1800,
        help="per-run wall-clock ceiling (s); n=16 is heavy. Tune after the "
             "calibration run.")
    parser.add_argument(
        "--max-runs", type=int, default=0,
        help=("at most this many runs this invocation, then stop cleanly "
              "(0 = no cap). Resume picks up from the ledger. Use multiples of "
              "~3-4 to stop on a balanced boundary."))
    args = parser.parse_args()

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    specs = build_specs()
    launcher = ClaudeCodeLauncher(model=args.model, timeout_s=args.timeout)
    runner = ExperimentRunner(
        args.experiment_root, launcher, repo_root=repo_root)

    pending = runner.ledger.pending(specs)
    cap_note = (f" (this invocation capped at {args.max_runs})"
                if args.max_runs else "")
    print(f"H8 process_billing scaling arm: {len(specs)} runs planned, "
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
                print(
                    f"\nPAUSING BATCH: {consecutive_fast_errors} consecutive "
                    f"runs errored in under {RATE_LIMIT_FAST_ERROR_S:.0f}s. "
                    f"Rate-limit cascade signature. Re-run when the "
                    f"subscription window resets.\n", flush=True)
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
