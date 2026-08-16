"""The configuration matrix and its expansion into runs.

PLAN.md crosses three axes: agent count (1, 2, 4, 8), topology (solo,
orchestrator, peer) and artefact policy (forbidden, allowed, mandatory). The
full cross product is 4 x 3 x 3 = 36 cells. PLAN.md names two degenerate
classes that are dropped, leaving the practical matrix of about 30 cells.

is_degenerate is the single documented place where the degeneracy rule lives.
It drops exactly the two classes PLAN.md names: a peer topology with a single
agent, and a mandatory artefact policy with a single agent (there is no
inter-agent state for either to constrain). This leaves 31 cells.
"""

from __future__ import annotations

from itertools import product

from agent_comms.runner.model import (
    AGENT_COUNTS, ARTEFACT_POLICIES, TOPOLOGIES, Cell, RunSpec,
)

# PLAN.md sets 20 repetitions per cell per task family.
DEFAULT_REPETITIONS = 20

# Family 1 distribution patterns, the values the task generator accepts.
FAMILY_1_PATTERNS = ("clean", "overlapping", "conflicting")


def is_degenerate(cell: Cell) -> bool:
    """Return True if a cell is one of the degenerate classes PLAN.md drops."""
    if cell.topology == "peer" and cell.agent_count == 1:
        return True
    if cell.artefact_policy == "mandatory" and cell.agent_count == 1:
        return True
    return False


def enumerate_cells() -> list[Cell]:
    """Return the practical configuration matrix, degenerate cells removed."""
    cells = []
    for count, topology, policy in product(
            AGENT_COUNTS, TOPOLOGIES, ARTEFACT_POLICIES):
        cell = Cell(count, topology, policy)
        if not is_degenerate(cell):
            cells.append(cell)
    return cells


def run_id(family: str, task_id: str, pattern: str, cell: Cell,
           replication: int) -> str:
    """Build the deterministic run identifier for one run."""
    return (f"{family}-{task_id}-{pattern}-{cell.label}"
            f"-r{replication:02d}")


def expand(cells, family, task_id, pattern, repetitions=DEFAULT_REPETITIONS,
           start=1) -> list[RunSpec]:
    """Expand cells into one RunSpec per cell per repetition."""
    specs = []
    for cell in cells:
        for rep in range(start, start + repetitions):
            specs.append(RunSpec(
                run_id=run_id(family, task_id, pattern, cell, rep),
                family=family, task_id=task_id, pattern=pattern,
                cell=cell, replication=rep))
    return specs


def family_1_specs(repetitions=DEFAULT_REPETITIONS, patterns=FAMILY_1_PATTERNS,
                    task_id="process_orders") -> list[RunSpec]:
    """Build the full Family 1 experiment plan for one task.

    A single agent cannot realise an overlapping or conflicting distribution,
    so single-agent cells (agent_count == 1) are emitted once, with the clean
    pattern.
    Multi-agent cells are emitted once per pattern.
    """
    return _matrix_specs("family-1", task_id, repetitions, patterns)


def family_2_main_matrix_specs(
        repetitions=DEFAULT_REPETITIONS,
        patterns=FAMILY_1_PATTERNS,
        task_id="summarise_transactions") -> list[RunSpec]:
    """Build the Family 2 main matrix: one task across every non-degenerate
    cell × pattern combination, mirroring Family 1's matrix.

    See `memory/experiments/family-2-full/matrix.md` for the design choice.
    The pattern handling mirrors family_1_specs: single-agent cells (n=1) are
    emitted only with the clean pattern, multi-agent cells once per pattern.
    """
    return _matrix_specs("family-2", task_id, repetitions, patterns)


def _matrix_specs(family, task_id, repetitions, patterns) -> list[RunSpec]:
    """Shared implementation for family_1_specs and family_2_main_matrix_specs."""
    specs = []
    for cell in enumerate_cells():
        cell_patterns = ("clean",) if cell.agent_count == 1 else patterns
        for pattern in cell_patterns:
            specs.extend(expand(
                [cell], family, task_id, pattern, repetitions))
    return specs
