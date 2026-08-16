"""The agent-to-component assignment algorithm.

Given a component count, an agent count and a distribution pattern, this
module produces the assignment of components to agents.

- clean: each component is held by exactly one agent.
- overlapping: a clean assignment, then a chosen set of components is each
  given to a second agent as well, as an identical copy.
- conflicting: a clean assignment, then a chosen set of components is each
  given to a second agent as a variant version that differs from the
  canonical one.

When the agent count is at least the component count, each of the first
components goes to one agent; any further agents start empty. When the agent
count is below the component count, components are distributed in contiguous
blocks so that each agent holds two or more.
"""

from __future__ import annotations

from dataclasses import dataclass

CLEAN = "clean"
OVERLAPPING = "overlapping"
CONFLICTING = "conflicting"
PATTERNS = (CLEAN, OVERLAPPING, CONFLICTING)


@dataclass(frozen=True)
class Holding:
    """One component held by one agent, optionally as a named variant."""

    component_index: int
    variant: str | None = None


def clean_partition(n_components: int, agent_count: int) -> list[list[int]]:
    """Return a list of length agent_count of component-index lists.

    Each component index appears in exactly one agent's list.
    """
    if agent_count < 1:
        raise ValueError("agent_count must be at least 1")
    if n_components < 1:
        raise ValueError("n_components must be at least 1")
    holdings: list[list[int]] = [[] for _ in range(agent_count)]
    if agent_count >= n_components:
        for i in range(n_components):
            holdings[i].append(i)
    else:
        for i in range(n_components):
            holdings[i * agent_count // n_components].append(i)
    return holdings


def _primary_holder(partition: list[list[int]], component_index: int) -> int:
    for agent, components in enumerate(partition):
        if component_index in components:
            return agent
    raise ValueError(f"component {component_index} is not assigned")


def _second_holder(primary: int, agent_count: int) -> int:
    if agent_count < 2:
        raise ValueError(
            "overlapping and conflicting patterns need at least 2 agents")
    return (primary + 1) % agent_count


def assign(n_components, agent_count, pattern,
           overlap_indices=(), conflict_specs=()) -> list[list[Holding]]:
    """Return the assignment as a list of length agent_count of Holding lists.

    overlap_indices: component indices to duplicate, for the overlapping
        pattern.
    conflict_specs: (component_index, variant_name) pairs, for the conflicting
        pattern. The primary holder keeps the canonical version; the second
        holder receives the named variant.
    """
    if pattern not in PATTERNS:
        raise ValueError(f"unknown pattern {pattern!r}")
    partition = clean_partition(n_components, agent_count)
    holdings: list[list[Holding]] = [
        [Holding(i) for i in components] for components in partition
    ]

    if pattern == OVERLAPPING:
        for index in overlap_indices:
            primary = _primary_holder(partition, index)
            holder = _second_holder(primary, agent_count)
            if all(h.component_index != index for h in holdings[holder]):
                holdings[holder].append(Holding(index))
    elif pattern == CONFLICTING:
        for index, variant in conflict_specs:
            primary = _primary_holder(partition, index)
            holder = _second_holder(primary, agent_count)
            holdings[holder].append(Holding(index, variant))
    return holdings
