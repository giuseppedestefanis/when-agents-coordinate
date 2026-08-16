"""Experiment runner (infrastructure component 4).

Orchestrates runs across the configuration matrix defined in PLAN.md. For each
run it generates the task instance (component 3), sets up an isolated working
directory, launches the agents with the message protocol server (component 1)
wired in, runs the verifier, feeds the session logs to the parser (component
2), and records the outcome in a resumable ledger.

The step that invokes Claude Code is held behind a pluggable launcher, because
the exact invocation mechanism is an open question; this keeps the
orchestration testable independently of it.

Public entry points: ExperimentRunner, LaunchOutcome, the configuration matrix
helpers in matrix, and prepare_run.

Modules:
- model: the matrix cell, run specification and run result data model.
- matrix: the configuration matrix and its expansion into runs.
- workspace: per-run working directory setup.
- verify: running the verifier for a finished run.
- ledger: the resumable record of executed runs.
- runner: the ExperimentRunner orchestrator and the launcher contract.
- launch: ClaudeCodeLauncher, the production launcher for solo and peer runs.
"""

from agent_comms.runner.launch import (
    ClaudeCodeLauncher, build_command, find_session_file, subscription_env,
)
from agent_comms.runner.ledger import Ledger
from agent_comms.runner.matrix import (
    DEFAULT_REPETITIONS, FAMILY_1_PATTERNS, enumerate_cells, expand,
    family_1_specs, family_2_main_matrix_specs, is_degenerate, run_id,
)
from agent_comms.runner.model import (
    ARTEFACT_POLICIES, Cell, RunResult, RunSpec, STATUS_ERROR, STATUS_OK,
    TOPOLOGIES,
)
from agent_comms.runner.runner import ExperimentRunner, LaunchOutcome
from agent_comms.runner.verify import VerifyResult, run_verifier
from agent_comms.runner.workspace import (
    RunLayout, lock_workspace_for_strict_forbidden, prepare_run,
)

__all__ = [
    "ExperimentRunner", "LaunchOutcome",
    "ClaudeCodeLauncher", "build_command", "find_session_file",
    "subscription_env",
    "Ledger", "RunLayout", "prepare_run",
    "lock_workspace_for_strict_forbidden",
    "run_verifier", "VerifyResult",
    "Cell", "RunSpec", "RunResult", "STATUS_OK", "STATUS_ERROR",
    "TOPOLOGIES", "ARTEFACT_POLICIES",
    "enumerate_cells", "expand", "family_1_specs",
    "family_2_main_matrix_specs",
    "is_degenerate", "run_id",
    "DEFAULT_REPETITIONS", "FAMILY_1_PATTERNS",
]
