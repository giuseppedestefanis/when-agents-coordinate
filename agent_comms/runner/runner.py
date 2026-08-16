"""The experiment runner (infrastructure component 4).

ExperimentRunner orchestrates runs across the configuration matrix. For each
run it:

1. prepares an isolated run directory and generates the task instance
   (component 3, the task generator);
2. launches the agents through a pluggable launcher, with the message protocol
   server (component 1) wired in for multi-agent runs;
3. runs the verifier against the produced solution;
4. feeds the session logs and the message log to the session parser
   (component 2), which writes the run's CSV datasets;
5. records the outcome in the ledger and writes result.json.

After a batch, the per-run datasets are concatenated into master datasets.

The launcher

The step that actually invokes Claude Code is deliberately pluggable. The exact
invocation mechanism for Claude Code from a controller process is an open
question (see memory/open-questions.md), and isolating it behind a launcher
keeps the orchestration testable without it. A launcher is any callable:

    launcher(layout, spec) -> LaunchOutcome

The launcher is responsible for running the agents. Each agent acts in
layout.workspace_dir, is given the prompt at its AgentSetup.prompt_path and,
when present, the MCP configuration at its AgentSetup.mcp_config_path, and is
expected to leave its Claude Code session JSONL file in layout.sessions_dir.
The launcher returns a LaunchOutcome listing those session files.
ClaudeCodeLauncher in launch.py is the production launcher: it drives the
`claude` command line for the solo and peer topologies.
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field

from agent_comms.parser import combine_datasets, parse_run
from agent_comms.runner.ledger import Ledger
from agent_comms.runner.model import RunResult, STATUS_ERROR, STATUS_OK
from agent_comms.runner.verify import run_verifier
from agent_comms.runner.workspace import prepare_run
from agent_comms.task_generator.library import role_names_for

# Rate-limit cascade detection (see run_all below). When the subscription
# session limit hits, every subsequent run errors within a few seconds because
# the agents cannot authenticate. The runner detects this signature and pauses
# the batch rather than blasting through hundreds of error'd runs. Empirically
# a real run takes at least tens of seconds (usually >= 60s for a multi-agent
# run); an error that returns in under ten seconds is almost certainly a
# rate-limit reject, a process spawn failure or a configuration problem worth
# pausing for. Three consecutive instances is the trigger.
RATE_LIMIT_FAST_ERROR_S = 10.0
RATE_LIMIT_CONSECUTIVE_THRESHOLD = 3


@dataclass
class LaunchOutcome:
    """What a launcher returns after running the agents of one run.

    sessions: list of {"agent_id": str, "path": str}, one per session JSONL
        file produced, in the form the session parser expects.
    wall_time_s: wall-clock duration of the agent run.
    error: a message if the launch failed, otherwise None.
    """

    sessions: list = field(default_factory=list)
    wall_time_s: float = 0.0
    error: str | None = None


class ExperimentRunner:
    """Orchestrates runs across the configuration matrix.

    experiment_root holds the runs, the ledger and the master datasets:

        <experiment_root>/
          runs/        one directory per run
          master/      the combined CSV datasets
          ledger.json  the resumable run ledger
          ledger.csv   a flat CSV view of the ledger
    """

    def __init__(self, experiment_root, launcher, repo_root=None,
                 python=None, verifier_timeout=300, post_prepare=None):
        self.experiment_root = os.path.abspath(experiment_root)
        self.launcher = launcher
        self.repo_root = repo_root or os.getcwd()
        self.python = python
        self.verifier_timeout = verifier_timeout
        # post_prepare is an optional callable (layout, spec) -> None invoked
        # after prepare_run and before the launcher. It is the hook the
        # forbidden-policy enforcement ablation uses to lock the workspace.
        self.post_prepare = post_prepare
        self.runs_root = os.path.join(self.experiment_root, "runs")
        self.master_dir = os.path.join(self.experiment_root, "master")
        os.makedirs(self.runs_root, exist_ok=True)
        self.ledger = Ledger(os.path.join(self.experiment_root, "ledger.json"))

    def run_one(self, spec, task) -> RunResult:
        """Execute one run and return its RunResult."""
        layout = prepare_run(
            spec, task, self.runs_root, repo_root=self.repo_root,
            python=self.python or sys.executable)
        if self.post_prepare is not None:
            self.post_prepare(layout, spec)

        started = time.time()
        outcome = None
        try:
            outcome = self.launcher(layout, spec)
        except Exception as exc:  # a launcher fault must not abort the batch
            result = RunResult(
                spec.run_id, STATUS_ERROR, run_dir=layout.run_dir,
                wall_time_s=round(time.time() - started, 3),
                error=f"launcher raised: {exc}")
            self._finish(spec, layout, result, None, task)
            return result

        if outcome.error:
            result = RunResult(
                spec.run_id, STATUS_ERROR, run_dir=layout.run_dir,
                wall_time_s=outcome.wall_time_s, error=outcome.error)
            self._finish(spec, layout, result, outcome, task)
            return result

        verdict = run_verifier(
            layout, python=self.python, timeout=self.verifier_timeout)
        result = RunResult(
            run_id=spec.run_id, status=STATUS_OK,
            success=verdict.success, tests_passed=verdict.passed,
            tests_failed=verdict.failed, tests_errors=verdict.errors,
            wall_time_s=outcome.wall_time_s, error=verdict.error,
            run_dir=layout.run_dir)
        self._finish(spec, layout, result, outcome, task)
        return result

    def run_all(self, specs, task, resume=True, combine_every=25,
                verbose=False) -> list:
        """Execute a batch of runs, then combine their datasets.

        resume: when True, runs already complete in the ledger are skipped.
        combine_every: rebuild the master CSVs after every N completed runs,
            so the master stays fresh during a long batch instead of being
            rebuilt only at the end. The combine is best-effort: a failure
            does not abort the batch. Set to 0 to disable.
        verbose: print one progress line per run (run id, status, wall
            time, error if any). Off by default to keep the existing test
            harness quiet; production scripts pass verbose=True.

        Rate-limit cascade detection. If RATE_LIMIT_CONSECUTIVE_THRESHOLD
        consecutive runs error in under RATE_LIMIT_FAST_ERROR_S seconds,
        the batch is paused and the function returns the results collected
        so far. The pattern is the signature of a subscription rate-limit
        hitting mid-batch (every spawned agent process fails immediately).
        Without this guard the runner would blast through every remaining
        spec and mark each as `error`; the resume mechanism still works
        but the cascade wastes time and obscures the actual run state.
        Re-run the script after the subscription window resets; the
        ledger picks up the errored runs.
        """
        todo = self.ledger.pending(specs) if resume else list(specs)
        n_todo = len(todo)
        results = []
        consecutive_fast_errors = 0

        for i, spec in enumerate(todo, 1):
            if verbose:
                print(f"[{i}/{n_todo}] {spec.run_id}", flush=True)
            result = self.run_one(spec, task)
            results.append(result)
            if verbose:
                print(
                    f"    status={result.status} success={result.success} "
                    f"passed={result.tests_passed} "
                    f"failed={result.tests_failed} "
                    f"wall={result.wall_time_s}s",
                    flush=True)
                if result.error:
                    print(f"    error: {result.error}", flush=True)

            if (result.status == STATUS_ERROR
                    and result.wall_time_s < RATE_LIMIT_FAST_ERROR_S):
                consecutive_fast_errors += 1
                if (consecutive_fast_errors
                        >= RATE_LIMIT_CONSECUTIVE_THRESHOLD):
                    msg = (
                        f"PAUSING BATCH: {consecutive_fast_errors} "
                        f"consecutive runs errored in under "
                        f"{RATE_LIMIT_FAST_ERROR_S:.0f}s. This is the "
                        f"rate-limit cascade signature. Re-run the script "
                        f"when the subscription window resets; the ledger "
                        f"will resume from the errored runs."
                    )
                    if verbose:
                        print(f"\n{msg}\n", flush=True)
                    break
            else:
                consecutive_fast_errors = 0

            if combine_every and i % combine_every == 0:
                try:
                    self.combine()
                except Exception as exc:
                    if verbose:
                        print(f"    (combine warning: {exc})", flush=True)

        try:
            self.combine()
        except Exception:
            pass  # combine at end is best-effort; the master may already be fresh
        self.ledger.write_csv(
            os.path.join(self.experiment_root, "ledger.csv"))
        return results

    def combine(self) -> dict:
        """Concatenate every recorded run's datasets into the master set."""
        run_dirs = []
        for record in self.ledger.records.values():
            datasets = os.path.join(record.get("run_dir", ""), "datasets")
            if os.path.isdir(datasets):
                run_dirs.append(datasets)
        return combine_datasets(run_dirs, self.master_dir)

    def _finish(self, spec, layout, result, outcome, task) -> None:
        """Parse the run, write result.json and update the ledger.

        The parser is invoked only on STATUS_OK results. On STATUS_ERROR the
        launcher either failed outright or exited fast, and any session
        files left in layout.sessions_dir are partial. Parsing those
        would write a zero-or-near-zero-count row to the run's
        datasets/runs.csv that the master CSV later picks up as a
        ghost row indistinguishable from a real low-activity run. The
        cell-level analysis then averages over the contamination. The
        ledger and result.json still record the error verbatim, so
        nothing about the run's status is lost; only the per-run
        dataset is omitted, and the resume mechanism overwrites it
        with the real dataset when the run is retried.
        """
        if (result.status == STATUS_OK
                and outcome is not None and outcome.sessions):
            try:
                message_log = (layout.message_log
                               if os.path.exists(layout.message_log)
                               else None)
                # Augment the spec-derived run_record with the per-task
                # addressable role names so the parser can classify
                # message recipients as TARGET_KIND_ROLE rather than
                # TARGET_KIND_UNKNOWN. role_names_for returns [] for
                # Family 1 tasks (no addressable role names surfaced in
                # the prompts); see memory/decisions.md 2026-05-30 for
                # the convention.
                run_record = spec.run_record(success=result.success)
                run_record["role_names"] = role_names_for(task)
                parse_run(
                    spec.run_id, outcome.sessions, layout.datasets_dir,
                    message_log=message_log,
                    run_record=run_record)
            except Exception as exc:  # parsing must not abort the batch
                result.error = (
                    f"{result.error + ' | ' if result.error else ''}"
                    f"parser error: {exc}")

        with open(layout.result_path, "w", encoding="utf-8") as fh:
            json.dump(result.to_dict(), fh, indent=2)
        self.ledger.update(spec, result)
