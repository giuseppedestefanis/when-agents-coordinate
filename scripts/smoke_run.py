#!/usr/bin/env python3
"""Smoke test for the experiment runner: one Family 1 run, end to end.

This script invokes the real `claude` command line. By default it runs on the
Claude subscription plan: the launcher strips ANTHROPIC_API_KEY, so the run
does not bill a metered API key. The machine must be signed in to Claude Code
with a Claude subscription. It is a manual check, not part of the automated
test suite. It runs a single Family 1 run through the full pipeline: instance
generation (component 3), agent launch with the message protocol (component
1), the verifier, and the parser (component 2), and prints the result.

PLAN.md flags the message protocol as the single point of failure and asks for
a small end-to-end test before the full schedule. This script is that test.
After a peer run, inspect <run directory>/messages.jsonl to confirm the agents
used the message tool, and <run directory>/datasets/edges.csv for the graph.

Usage:

    .venv/bin/python scripts/smoke_run.py --model claude-opus-4-7

The run output, including the CSV datasets, is written under the experiment
root (data/smoke-run/ by default).
"""

import argparse
import os
import sys

# Make the repository importable when the script is run directly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_comms.runner import (
    Cell, ClaudeCodeLauncher, ExperimentRunner, expand,
)
from agent_comms.task_generator import get_task


def main():
    parser = argparse.ArgumentParser(
        description="Run one Family 1 run end to end against the real claude.")
    parser.add_argument("--experiment-root", default="data/smoke-run")
    parser.add_argument("--model", default=None,
                        help="model identifier to pin, e.g. claude-opus-4-7")
    parser.add_argument("--agents", type=int, default=2,
                        choices=[1, 2, 4, 8])
    parser.add_argument("--topology", default="peer",
                        choices=["solo", "peer", "orchestrator"])
    parser.add_argument("--policy", default="allowed",
                        choices=["forbidden", "allowed", "mandatory"])
    parser.add_argument("--pattern", default="clean",
                        choices=["clean", "overlapping", "conflicting"])
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cell = Cell(args.agents, args.topology, args.policy)
    spec = expand([cell], "family-1", "process_orders", args.pattern, 1)[0]
    task = get_task("process_orders")

    launcher = ClaudeCodeLauncher(model=args.model, timeout_s=args.timeout)
    runner = ExperimentRunner(
        args.experiment_root, launcher, repo_root=repo_root)

    print(f"running {spec.run_id}")
    result = runner.run_one(spec, task)

    print(f"status:        {result.status}")
    print(f"success:       {result.success}")
    print(f"tests passed:  {result.tests_passed}")
    print(f"tests failed:  {result.tests_failed}")
    print(f"wall time (s): {result.wall_time_s}")
    if result.error:
        print(f"error:         {result.error}")
    print(f"run directory: {result.run_dir}")
    print(f"ledger:        {runner.ledger.summary()}")


if __name__ == "__main__":
    main()
