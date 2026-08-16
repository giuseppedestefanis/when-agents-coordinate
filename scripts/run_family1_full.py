#!/usr/bin/env python3
"""Family 1 full configuration-matrix schedule.

Runs the `process_orders` task across every non-degenerate cell of the
configuration matrix and every applicable distribution pattern, N
repetitions per (cell, pattern). The cell enumeration and the
solo-only-clean rule live in `agent_comms/runner/matrix.py`
(`family_1_specs`); this script wires the runner, the launcher and the
ledger around it.

Decisions captured in `memory/decisions.md`:

  * **N = 10 first, top up high-variance cells to 20** (Bai26's lower
    defensible bound; staged design with the ledger making top-ups
    mechanically trivial).
  * **Run-level parallelism not added now** (the measured pilot
    bottleneck is the per-account session limit, not wall clock).
  * **Model pinned to claude-sonnet-4-6** (every prior batch used it;
    cross-cell comparisons require a fixed model; the pilot showed
    Sonnet is sufficient for Family 1 once the spec is correct).

Runs on the Claude subscription plan, like the other scripts in this
folder (the launcher strips `ANTHROPIC_API_KEY`). The machine must be
signed in to Claude Code with a Claude subscription. The batch is
resumable through the ledger: an interrupted run is re-picked up by
running the script again.

Usage::

    .venv/bin/python scripts/run_family1_full.py
    .venv/bin/python scripts/run_family1_full.py --reps 10
    .venv/bin/python scripts/run_family1_full.py --reps 10 --start 11   # top-up
    .venv/bin/python scripts/run_family1_full.py --only-cell-pattern \
        process_orders-clean-a4-orchestrator-forbidden --reps 1         # smoke

For the top-up step (running r11..r20 only on selected cells), use
``--start 11`` and filter with ``--only-cell-pattern`` repeated as
needed. The top-up cells are chosen from the analysis of the first
ten-rep pass, not picked here.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_comms.runner import (
    ClaudeCodeLauncher, ExperimentRunner, expand, family_1_specs,
)
from agent_comms.runner.matrix import FAMILY_1_PATTERNS, enumerate_cells
from agent_comms.task_generator import get_task


def build_specs(reps, start, only_cell_patterns, task_id):
    """Build the run specs, applying the cell-and-pattern filter if any.

    When `start` is 1 and there is no filter, this is exactly
    `family_1_specs(repetitions=reps)`. For top-ups, `start` is set to
    the next repetition number and `expand` is called per (cell,
    pattern) directly so the start parameter is honoured.
    """
    if start == 1 and not only_cell_patterns:
        return family_1_specs(repetitions=reps, task_id=task_id)
    specs = []
    for cell in enumerate_cells():
        patterns = ("clean",) if cell.agent_count == 1 else FAMILY_1_PATTERNS
        for pattern in patterns:
            label = f"{task_id}-{pattern}-{cell.label}"
            if only_cell_patterns and label not in only_cell_patterns:
                continue
            specs.extend(expand(
                [cell], "family-1", task_id, pattern, reps, start=start))
    return specs


def main():
    parser = argparse.ArgumentParser(
        description="Family 1 full configuration-matrix schedule.")
    parser.add_argument(
        "--experiment-root", default="data/family-1-full",
        help="output directory for the batch (per-run dirs, master, ledger)")
    parser.add_argument("--model", default="claude-sonnet-4-6")
    parser.add_argument("--timeout", type=int, default=900,
                        help="per-run wall-clock ceiling in seconds")
    parser.add_argument("--reps", type=int, default=10,
                        help="repetitions per cell-and-pattern combination")
    parser.add_argument("--start", type=int, default=1,
                        help="first replication number (use 11 for top-up)")
    parser.add_argument("--task-id", default="process_orders")
    parser.add_argument(
        "--only-cell-pattern", action="append", default=[],
        metavar="LABEL",
        help=("filter to specific cell-and-pattern combinations; pass the "
              "label after the task id, e.g. "
              "'process_orders-clean-a4-orchestrator-forbidden'. May be "
              "repeated. Default: all combinations."))
    args = parser.parse_args()

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    specs = build_specs(
        args.reps, args.start, args.only_cell_pattern, args.task_id)
    task = get_task(args.task_id)
    launcher = ClaudeCodeLauncher(model=args.model, timeout_s=args.timeout)
    runner = ExperimentRunner(
        args.experiment_root, launcher, repo_root=repo_root)

    pending = runner.ledger.pending(specs)
    print(f"Family 1 full schedule: {len(specs)} runs planned, "
          f"{len(pending)} pending, model {args.model}, "
          f"start replication {args.start}", flush=True)
    if args.only_cell_pattern:
        print(f"  filter: {args.only_cell_pattern}", flush=True)

    # The runner's run_all loop handles per-run progress printing, periodic
    # master-CSV rebuilds (every 25 runs by default) so the analysis pipeline
    # sees fresh data while the batch is going, and rate-limit cascade
    # detection so a subscription session-limit reject does not turn into
    # hundreds of error'd specs.
    runner.run_all(specs, task, resume=True, combine_every=25, verbose=True)

    print(f"done. summary: {runner.ledger.summary()}", flush=True)
    print(f"master datasets: {runner.master_dir}", flush=True)


if __name__ == "__main__":
    main()
