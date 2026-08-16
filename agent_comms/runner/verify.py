"""Running the verifier for a finished run.

The verifier is the deterministic pytest test suite for the task. It is run in
a fresh subprocess against the run's own workspace directory, so that one
run's solution.py and any cached import cannot leak into another run.

The verifier file imports the produced code with `from solution import ...`.
The subprocess therefore runs with the run's workspace directory on
PYTHONPATH, which is where the agents are asked to write solution.py. The
verifier itself sits in the run's verifier/ directory, outside the workspace,
so the agents never see the test suite.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass

_PASSED = re.compile(r"(\d+) passed")
_FAILED = re.compile(r"(\d+) failed")
_ERRORS = re.compile(r"(\d+) error")

# A run's verifier should not take long. The default guards against an agent
# solution that hangs.
DEFAULT_TIMEOUT_S = 300


@dataclass
class VerifyResult:
    """The outcome of running a verifier."""

    success: bool
    passed: int = 0
    failed: int = 0
    errors: int = 0
    returncode: int | None = None
    output: str = ""
    error: str | None = None


def _count(pattern, text) -> int:
    match = pattern.search(text)
    return int(match.group(1)) if match else 0


def run_verifier(layout, python=None, timeout=DEFAULT_TIMEOUT_S) -> VerifyResult:
    """Run the verifier for a run and return a VerifyResult.

    layout: the RunLayout for the run.
    python: the interpreter to run pytest with. Defaults to the current one.
    timeout: seconds before the verifier subprocess is killed.
    """
    python = python or sys.executable

    if not os.path.exists(layout.verifier_path):
        return VerifyResult(
            False, error=f"verifier not found: {layout.verifier_path}")
    if not os.path.exists(layout.solution_path):
        return VerifyResult(
            False, error=f"solution not produced: {layout.solution_path}")

    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        p for p in (layout.workspace_dir, env.get("PYTHONPATH", "")) if p)

    command = [
        python, "-m", "pytest", layout.verifier_path,
        "-q", "--no-header", "-p", "no:cacheprovider",
    ]
    try:
        proc = subprocess.run(
            command, cwd=layout.verifier_dir, env=env,
            capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return VerifyResult(
            False, error=f"verifier timed out after {timeout}s")

    output = proc.stdout + proc.stderr
    return VerifyResult(
        success=(proc.returncode == 0),
        passed=_count(_PASSED, output),
        failed=_count(_FAILED, output),
        errors=_count(_ERRORS, output),
        returncode=proc.returncode,
        output=output[-4000:],
    )
