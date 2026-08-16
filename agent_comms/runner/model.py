"""Data model for the experiment runner.

Defines the configuration matrix cell, the specification of a single run, and
the result of executing one run. PLAN.md fixes three matrix axes: agent count,
topology and artefact policy. A run is one cell of that matrix combined with a
task, a Family 1 distribution pattern and a repetition index.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

# The configuration matrix axes, from PLAN.md.
AGENT_COUNTS = (1, 2, 4, 8)
TOPOLOGIES = ("solo", "orchestrator", "peer")
ARTEFACT_POLICIES = ("forbidden", "allowed", "mandatory")

# Agent counts a Cell will accept. The main configuration matrix
# (`enumerate_cells`) uses AGENT_COUNTS only; the 16-agent scaling arm (H8) is
# collected as a standalone batch via its own run script (mirroring the H7
# compute_invoices arm), so 16 is a valid count for a hand-built Cell WITHOUT
# becoming part of the enumerated main matrix.
VALID_AGENT_COUNTS = (1, 2, 4, 8, 16)

# Run status. status records whether the orchestration of a run completed;
# success (on RunResult) records the verifier verdict and is only meaningful
# when status is STATUS_OK.
STATUS_OK = "ok"        # the run was orchestrated and the verifier produced a verdict
STATUS_ERROR = "error"  # the run failed before a verdict could be reached


@dataclass(frozen=True)
class Cell:
    """One cell of the configuration matrix."""

    agent_count: int
    topology: str
    artefact_policy: str

    def __post_init__(self) -> None:
        if self.agent_count not in VALID_AGENT_COUNTS:
            raise ValueError(
                f"agent_count must be one of {VALID_AGENT_COUNTS}, "
                f"got {self.agent_count!r}")
        if self.topology not in TOPOLOGIES:
            raise ValueError(
                f"topology must be one of {TOPOLOGIES}, "
                f"got {self.topology!r}")
        if self.artefact_policy not in ARTEFACT_POLICIES:
            raise ValueError(
                f"artefact_policy must be one of {ARTEFACT_POLICIES}, "
                f"got {self.artefact_policy!r}")

    @property
    def label(self) -> str:
        """A short filesystem-safe label, for example a4-orchestrator-allowed."""
        return f"a{self.agent_count}-{self.topology}-{self.artefact_policy}"


@dataclass(frozen=True)
class RunSpec:
    """The specification of one run: a matrix cell plus a task and repetition.

    run_id is a deterministic, unique, filesystem-safe identifier and is also
    the name of the run's directory under the experiment root.
    """

    run_id: str
    family: str
    task_id: str
    pattern: str
    cell: Cell
    replication: int

    def run_record(self, success=None) -> dict:
        """Return the run metadata dict consumed by the session parser.

        The fields match the configuration and outcome columns of runs.csv.
        """
        return {
            "family": self.family,
            "instance": f"{self.task_id}/{self.pattern}",
            "agent_count": self.cell.agent_count,
            "topology": self.cell.topology,
            "artefact_policy": self.cell.artefact_policy,
            "success": success,
        }


@dataclass
class RunResult:
    """The result of executing one run."""

    run_id: str
    status: str
    success: bool = False
    tests_passed: int = 0
    tests_failed: int = 0
    tests_errors: int = 0
    wall_time_s: float = 0.0
    error: str | None = None
    run_dir: str = ""

    def to_dict(self) -> dict:
        return asdict(self)
