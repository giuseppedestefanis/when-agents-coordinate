#!/usr/bin/env python3
"""Run the Family 1 broader pilot batch.

Runs a 36-run pilot of Family 1 (the process_orders task) through the
experiment runner on the Claude subscription plan. The batch is a
one-factor-at-a-time design around a four-agent baseline, so each axis of the
configuration matrix is exercised:

- artefact policy varied (forbidden, allowed, mandatory) at four agents, clean
  distribution, for the peer and orchestrator topologies;
- distribution pattern varied (overlapping, conflicting) at four agents,
  allowed policy, for the peer and orchestrator topologies;
- agent count varied (2, 8) for the peer topology, allowed policy, clean
  distribution.

That is 12 matrix-and-pattern cells, 3 repetitions each. The batch is
resumable: if it is interrupted, run it again and the runner skips the runs
already recorded as complete in the ledger.

This invokes the real `claude` command line on the Claude subscription plan
(it does not bill a metered API key). The machine must be signed in to Claude
Code with a Claude subscription. The batch is sequential and takes a few
hours. The model is pinned for every run and recorded per turn in turns.csv.

Usage:

    .venv/bin/python scripts/run_pilot.py

The default model is claude-sonnet-4-6, which is light on the subscription's
usage limits and adequate for a pilot whose purpose is to check that the
expected graph signatures appear. Pass --model to pin a different model; use a
fresh --experiment-root if you do, so a batch is not mixed across models.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_comms.runner import Cell, ClaudeCodeLauncher, ExperimentRunner, expand
from agent_comms.task_generator import get_task

REPETITIONS = 3


def pilot_specs():
    """Build the Family 1 broader pilot batch: 12 cells, 3 repetitions each."""
    specs = []
    # Vary the artefact policy: four agents, clean distribution, both topologies.
    for topology in ("peer", "orchestrator"):
        for policy in ("forbidden", "allowed", "mandatory"):
            specs += expand([Cell(4, topology, policy)], "family-1",
                            "process_orders", "clean", REPETITIONS)
    # Vary the distribution pattern: four agents, allowed policy, both topologies.
    for topology in ("peer", "orchestrator"):
        for pattern in ("overlapping", "conflicting"):
            specs += expand([Cell(4, topology, "allowed")], "family-1",
                            "process_orders", pattern, REPETITIONS)
    # Vary the agent count: peer topology, allowed policy, clean distribution.
    for count in (2, 8):
        specs += expand([Cell(count, "peer", "allowed")], "family-1",
                        "process_orders", "clean", REPETITIONS)
    return specs


def main():
    parser = argparse.ArgumentParser(
        description="Run the Family 1 broader pilot batch.")
    parser.add_argument("--experiment-root", default="data/family-1-pilot")
    parser.add_argument("--model", default="claude-sonnet-4-6",
                        help="model identifier pinned for every agent")
    parser.add_argument("--timeout", type=int, default=900,
                        help="per-run wall-clock ceiling in seconds")
    args = parser.parse_args()

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    specs = pilot_specs()
    task = get_task("process_orders")
    launcher = ClaudeCodeLauncher(model=args.model, timeout_s=args.timeout)
    runner = ExperimentRunner(
        args.experiment_root, launcher, repo_root=repo_root)

    pending = runner.ledger.pending(specs)
    print(f"pilot batch: {len(specs)} runs, {len(pending)} pending, "
          f"model {args.model}", flush=True)
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
