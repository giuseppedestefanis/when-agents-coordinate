"""Task data model for the task generator.

Two task shapes are supported. A Family 1 task is a single Python function
whose specification is split into components; every component is part of the
same deliverable file. A Family 2 task is a sequential pipeline where each
component (step) has its own deliverable file, plus a shared pipeline.py
that composes them.

Each component is the unit of distribution across agents.
"""

from __future__ import annotations

from dataclasses import dataclass, field

FAMILY_1 = "family-1"
FAMILY_2 = "family-2"


@dataclass
class Component:
    """One component of a task specification.

    label: a short name, for example "Validation rules" or "Step 2".
    text: the canonical component block, the version that matches the verifier.
    variants: optional alternative versions keyed by a variant name, used for
        conflicting distributions. A variant is a slightly different version
        of the component that does not match the verifier.
    deliverable_path: for Family 2 tasks, the file this component (step)
        produces, for example "validate.py". Empty for Family 1 tasks,
        where every component contributes to the same solution_path.
    """

    label: str
    text: str
    variants: dict = field(default_factory=dict)
    deliverable_path: str = ""

    def version(self, variant=None) -> str:
        """Return the canonical text, or a named variant."""
        if variant is None:
            return self.text
        if variant not in self.variants:
            raise KeyError(
                f"component {self.label!r} has no variant {variant!r}")
        return self.variants[variant]

    def has_variants(self) -> bool:
        return bool(self.variants)


@dataclass
class Task:
    """A task specification split into components.

    family: "family-1" (single-file deliverable, default) or "family-2"
        (chain-of-steps deliverable). The prompt rendering, the policy
        clauses and the runner's expectations dispatch on this field.
    function_name: for Family 1, the function the team implements (e.g.
        "process_orders"). For Family 2, the team-level pipeline function
        (e.g. "summarise_transactions").
    solution_path: for Family 1, the single deliverable file (solution.py).
        For Family 2, the pipeline file (pipeline.py); each component's
        deliverable_path holds its own step file.
    team_signature: for Family 2, the multi-line signature of the team's
        pipeline function as it appears in the agent prompts (the full
        return-type expression so the prompt is self-documenting). Empty
        for Family 1, where the function_name alone identifies the
        deliverable.
    verifier_path and reference_solution_path point to the runnable artefacts
        in the repository; the generator references them rather than copying,
        so there is a single source of truth.
    """

    task_id: str
    function_name: str
    solution_path: str
    components: list[Component]
    verifier_path: str = ""
    reference_solution_path: str = ""
    family: str = FAMILY_1
    team_signature: str = ""

    @property
    def n_components(self) -> int:
        return len(self.components)

    def variant_components(self) -> list[int]:
        """Return the indices of components that have variants."""
        return [i for i, c in enumerate(self.components) if c.has_variants()]

    def deliverable_paths(self) -> list[str]:
        """Return the full list of files the team's deliverable comprises.

        For Family 1 this is just `[solution_path]`. For Family 2 it is the
        list of step deliverables plus `pipeline.py`, in component order.
        Useful for the forbidden-policy clause and for the runner manifest.
        """
        if self.family == FAMILY_2:
            step_paths = [
                c.deliverable_path for c in self.components
                if c.deliverable_path
            ]
            # `solution_path` for Family 2 is pipeline.py; include it last.
            if self.solution_path and self.solution_path not in step_paths:
                step_paths.append(self.solution_path)
            return step_paths
        return [self.solution_path]
