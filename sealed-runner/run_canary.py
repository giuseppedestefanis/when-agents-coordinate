#!/usr/bin/env python3
"""Run the sealed canary.

This drives the released Family 1 runner unchanged, except that the
per-run ``prepare_run`` is wrapped at run time with the Phase-0 seal
(see seal.py): the agents' workspace is relocated to a control tree and
the familiar sibling paths are filled with decoys. Nothing in the
released packages is modified on disk.

The real verifier, instance manifest and prompts stay in the run
directory under ``--experiment-root`` and are used for scoring and
parsing exactly as before. The decoys live under ``--control-root``.

Usage (run from the paper_Agents repo so tasks/ and .venv resolve)::

    .venv/bin/python \\
      ../improvement_20_july/sealed-runner/run_canary.py \\
      --experiment-root ../improvement_20_july/test-output/canary \\
      --control-root   ../improvement_20_july/test-output/canary/_control \\
      --only-cell-pattern process_orders-clean-a8-peer-allowed \\
      --reps 2 --start 101 --model claude-sonnet-4-6

After it finishes, run check_reads.py against the same --experiment-root
and --control-root to classify every file read.
"""

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# The repo whose agent_comms/, tasks/ and .venv produced the paper's data.
PAPER_AGENTS = os.path.abspath(os.path.join(HERE, "..", "..", "paper_Agents"))

sys.path.insert(0, PAPER_AGENTS)
sys.path.insert(0, os.path.join(PAPER_AGENTS, "scripts"))
sys.path.insert(0, HERE)

from agent_comms.runner import ClaudeCodeLauncher, ExperimentRunner  # noqa: E402
import agent_comms.runner.runner as runner_mod  # noqa: E402
from agent_comms.task_generator import get_task  # noqa: E402
from run_family1_full import build_specs  # noqa: E402  (released, reused verbatim)

from seal import sealify  # noqa: E402


def install_seal(control_root):
    """Wrap the runner's prepare_run so every run gets the seal."""
    original = runner_mod.prepare_run

    def sealed_prepare(spec, task, runs_root, repo_root=None, python="python"):
        layout = original(
            spec, task, runs_root, repo_root=repo_root, python=python)
        return sealify(layout, control_root)

    runner_mod.prepare_run = sealed_prepare


def main():
    parser = argparse.ArgumentParser(description="Sealed canary run.")
    parser.add_argument("--experiment-root", required=True,
                        help="output dir for the REAL run tree (scoring, CSVs)")
    parser.add_argument("--control-root", required=True,
                        help="dir for the relocated workspaces and decoys")
    parser.add_argument("--model", default="claude-sonnet-4-6")
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--reps", type=int, default=2)
    parser.add_argument("--start", type=int, default=101)
    parser.add_argument("--task-id", default="process_orders")
    parser.add_argument("--only-cell-pattern", action="append", default=[],
                        metavar="LABEL")
    args = parser.parse_args()

    control_root = os.path.abspath(args.control_root)
    install_seal(control_root)

    specs = build_specs(
        args.reps, args.start, args.only_cell_pattern, args.task_id)
    task = get_task(args.task_id)
    launcher = ClaudeCodeLauncher(model=args.model, timeout_s=args.timeout)
    runner = ExperimentRunner(
        args.experiment_root, launcher, repo_root=PAPER_AGENTS)

    pending = runner.ledger.pending(specs)
    print(f"SEALED canary: {len(specs)} runs planned, {len(pending)} pending, "
          f"model {args.model}, start {args.start}", flush=True)
    print(f"  experiment-root (real): {os.path.abspath(args.experiment_root)}",
          flush=True)
    print(f"  control-root   (decoys): {control_root}", flush=True)
    if args.only_cell_pattern:
        print(f"  filter: {args.only_cell_pattern}", flush=True)

    runner.run_all(specs, task, resume=True, combine_every=25, verbose=True)

    print(f"done. summary: {runner.ledger.summary()}", flush=True)
    print(f"master datasets: {runner.master_dir}", flush=True)
    print("next: check_reads.py --experiment-root ... --control-root ...",
          flush=True)


if __name__ == "__main__":
    main()
