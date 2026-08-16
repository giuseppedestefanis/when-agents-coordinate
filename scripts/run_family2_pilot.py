#!/usr/bin/env python3
"""Run the Family 2 pilot batch.

Runs a 42-run pilot of Family 2 through the experiment runner on the Claude
subscription plan. The batch mirrors the Family 1 broader pilot's
one-factor-at-a-time design around a four-agent baseline, with an extra task-
variation axis because Family 2 has three distinct tasks (one for the
shared-task Instances 1, 3 and 5; one for the longer Instance 2; one for the
non-local-dependency Instance 4).

Cells exercised, all with three repetitions:

  - Artefact policy varied (forbidden, allowed, mandatory) at four agents,
    clean distribution, summarise_transactions, for the peer and
    orchestrator topologies. Six cells.
  - Distribution pattern varied (overlapping, conflicting) at four agents,
    allowed policy, summarise_transactions, for the peer and orchestrator
    topologies. Four cells.
  - Agent count varied (2, 8) for the peer topology, allowed policy, clean
    distribution, summarise_transactions. Two cells.
  - Task varied: compute_invoices (Instance 2, longer chain) and
    summarise_transactions_v2 (Instance 4, non-local CATEGORY_ORDER
    dependency) at four agents, peer, allowed, clean. Two cells.

Total: 14 cells x 3 repetitions = 42 runs.

The batch is resumable: if it is interrupted, run it again and the runner
skips the runs already recorded as complete in the ledger. The runner's
cascade detector pauses the batch cleanly if the subscription rate limit
hits mid-flight.

This invokes the real `claude` command line on the Claude subscription plan
(it does not bill a metered API key). The machine must be signed in to
Claude Code with a Claude subscription. The model is pinned for every run
and recorded per turn in turns.csv.

Usage:

    .venv/bin/python scripts/run_family2_pilot.py

The default model is claude-sonnet-4-6, matching the Family 1 schedule for
cross-family comparability. Pass --model to pin a different model; use a
fresh --experiment-root if you do, so a batch is not mixed across models.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_comms.runner import Cell, ClaudeCodeLauncher, ExperimentRunner, expand
from agent_comms.task_generator import get_task

REPETITIONS = 3
FAMILY = "family-2"

# The "shared" Family 2 task: used by Instances 1 (clean), 3 (overlapping)
# and 5 (conflicting), the way Family 1's process_orders is used.
SHARED_TASK = "summarise_transactions"
LONGER_TASK = "compute_invoices"            # Instance 2.
NON_LOCAL_TASK = "summarise_transactions_v2"  # Instance 4.


def pilot_specs():
    """Build the Family 2 pilot batch: 14 cells, 3 repetitions each."""
    specs = []

    # Artefact policy varied: four agents, clean, summarise_transactions,
    # both topologies. Six cells.
    for topology in ("peer", "orchestrator"):
        for policy in ("forbidden", "allowed", "mandatory"):
            specs += expand(
                [Cell(4, topology, policy)],
                FAMILY, SHARED_TASK, "clean", REPETITIONS)

    # Distribution pattern varied: four agents, allowed,
    # summarise_transactions, both topologies. Four cells.
    for topology in ("peer", "orchestrator"):
        for pattern in ("overlapping", "conflicting"):
            specs += expand(
                [Cell(4, topology, "allowed")],
                FAMILY, SHARED_TASK, pattern, REPETITIONS)

    # Agent count varied: peer, allowed, clean, summarise_transactions.
    # Two cells.
    for count in (2, 8):
        specs += expand(
            [Cell(count, "peer", "allowed")],
            FAMILY, SHARED_TASK, "clean", REPETITIONS)

    # Task varied at the baseline cell (4 agents, peer, allowed, clean).
    # Two cells.
    for task_id in (LONGER_TASK, NON_LOCAL_TASK):
        specs += expand(
            [Cell(4, "peer", "allowed")],
            FAMILY, task_id, "clean", REPETITIONS)

    return specs


def _task_for(spec):
    """Resolve the Task object the runner needs from a spec."""
    return get_task(spec.task_id)


def main():
    parser = argparse.ArgumentParser(
        description="Run the Family 2 pilot batch.")
    parser.add_argument("--experiment-root", default="data/family-2-pilot")
    parser.add_argument("--model", default="claude-sonnet-4-6",
                        help="model identifier pinned for every agent")
    parser.add_argument("--timeout", type=int, default=900,
                        help="per-run wall-clock ceiling in seconds")
    args = parser.parse_args()

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    specs = pilot_specs()
    launcher = ClaudeCodeLauncher(model=args.model, timeout_s=args.timeout)
    runner = ExperimentRunner(
        args.experiment_root, launcher, repo_root=repo_root)

    pending = runner.ledger.pending(specs)
    print(f"family-2 pilot: {len(specs)} runs, {len(pending)} pending, "
          f"model {args.model}", flush=True)

    # The runner's run_all helper handles the per-run loop, the resume,
    # periodic combines and rate-limit cascade detection. Different specs
    # may use different tasks (the three Family 2 tasks), so we call
    # run_one in a loop here and let the ledger handle the rest, rather
    # than pre-fixing one task for the whole batch.
    for i, spec in enumerate(pending, 1):
        print(f"[{i}/{len(pending)}] {spec.run_id}", flush=True)
        result = runner.run_one(spec, _task_for(spec))
        print(f"    status={result.status} success={result.success} "
              f"passed={result.tests_passed} failed={result.tests_failed} "
              f"wall={result.wall_time_s}s", flush=True)
        if result.error:
            print(f"    error: {result.error}", flush=True)
        # Best-effort periodic combine every 25 runs.
        if i % 25 == 0:
            try:
                runner.combine()
            except Exception as exc:
                print(f"    (combine warning: {exc})", flush=True)

    runner.combine()
    runner.ledger.write_csv(
        os.path.join(runner.experiment_root, "ledger.csv"))
    print(f"done. summary: {runner.ledger.summary()}", flush=True)
    print(f"master datasets: {runner.master_dir}", flush=True)


if __name__ == "__main__":
    main()
