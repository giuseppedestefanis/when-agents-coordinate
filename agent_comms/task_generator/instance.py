"""Prompt rendering and writing a run-ready instance directory.

generate_instance produces, for a task at a given agent count and distribution
pattern, an instance directory containing:

- prompts/agent-N.txt: one prompt per agent, parameterised by the components
  that agent holds. The prompt assigns no role, names no other agent and does
  not mention any communication mechanism beyond the message tool.
- instance.json: a manifest with the task identity, the parameters, the
  agent-to-component assignment and the paths to the verifier and reference
  solution. The experiment runner (component 4) consumes this manifest.

The Family 1 and Family 2 prompt templates differ. Family 1 frames the work
as a single function whose specification is distributed across components.
Family 2 frames the work as a chain of step functions composed by
pipeline.py: the team-level pipeline signature is shared, but the chain
length, each agent's position in the chain and the other agents'
specifications are explicitly withheld. The Family 2 framing is the
"interface negotiation in a known-sequential task" claim recorded in
memory/decisions.md (2026-05-23).
"""

from __future__ import annotations

import json
import os

from agent_comms.task_generator.distribution import (
    CONFLICTING, OVERLAPPING, assign,
)
from agent_comms.task_generator.model import FAMILY_2

PROMPT_TEMPLATE = """\
You are one of {agent_count} agents working together to implement a single \
Python function. No agent has the complete specification. Each agent has been \
given one or more parts of it.

The team's goal is to produce a correct, working implementation of the \
function {function_name} in the file {solution_path}, in the shared working \
directory. The implementation is correct only when it satisfies every part of \
the specification held across the team, not only the part or parts you hold.

The part or parts of the specification you have been given are:

{component_blocks}

The remaining parts are held by the other agents. Decide for yourself how to \
combine your part or parts with theirs and how to arrive at the finished \
implementation.
"""


FAMILY_2_PROMPT_TEMPLATE = """\
You are one of {agent_count} agents collaborating on a sequential software \
task. The team's deliverable is a function

{team_signature}

exposed by `{solution_path}`. The function is implemented as a chain of step \
functions, each in its own Python file. `{solution_path}` composes the step \
functions in order. Your contribution is one or more steps of the chain.

You do not know how many steps the chain has, where in the chain your step \
sits, or what the other steps do. You learn this through coordination with \
the other agents.

Your deliverable file{file_plural}: {deliverable_files}.

Your piece{piece_plural} of the specification:

{component_blocks}

Coordinate with the other agents through the message tool to agree on the \
chain order, the inter-step interfaces, and who writes `{solution_path}`.
"""


def _render_family_1_prompt(task, agent_count, held) -> str:
    blocks = []
    for holding in held:
        component = task.components[holding.component_index]
        blocks.append(
            f"--- {component.label} ---\n"
            f"{component.version(holding.variant)}")
    return PROMPT_TEMPLATE.format(
        agent_count=agent_count,
        function_name=task.function_name,
        solution_path=task.solution_path,
        component_blocks="\n\n".join(blocks) if blocks
        else "(no component assigned)")


def _render_family_2_prompt(task, agent_count, held) -> str:
    blocks = []
    deliverables = []
    for holding in held:
        component = task.components[holding.component_index]
        blocks.append(
            f"--- {component.label} ---\n"
            f"{component.version(holding.variant)}")
        if component.deliverable_path:
            deliverables.append(component.deliverable_path)
    n_held = len(held)
    return FAMILY_2_PROMPT_TEMPLATE.format(
        agent_count=agent_count,
        team_signature=task.team_signature,
        solution_path=task.solution_path,
        deliverable_files=", ".join(f"`{p}`" for p in deliverables)
        if deliverables else "(none directly assigned to you)",
        file_plural="s are" if len(deliverables) != 1 else " is named",
        piece_plural="s" if n_held != 1 else "",
        component_blocks="\n\n".join(blocks) if blocks
        else "(no component assigned)")


def render_prompt(task, agent_count, held) -> str:
    """Render the prompt for one agent.

    Dispatches to the Family 1 or Family 2 template based on `task.family`.

    held: a list of Holding for that agent.
    """
    if task.family == FAMILY_2:
        return _render_family_2_prompt(task, agent_count, held)
    return _render_family_1_prompt(task, agent_count, held)


def _default_overlap_indices(n_components: int) -> list[int]:
    """Choose components to duplicate for an overlapping instance."""
    count = min(2, max(1, n_components - 1))
    return list(range(1, 1 + count))


def _default_conflict_specs(task) -> list[tuple]:
    """Choose components and variants for a conflicting instance.

    Uses the first component that defines a variant, with its first variant.
    """
    specs = []
    for index in task.variant_components():
        variant = next(iter(task.components[index].variants))
        specs.append((index, variant))
        break
    return specs


def generate_instance(task, agent_count, pattern, out_dir,
                       overlap_indices=None, conflict_specs=None) -> dict:
    """Generate a run-ready instance directory and return its manifest."""
    if pattern == OVERLAPPING and overlap_indices is None:
        overlap_indices = _default_overlap_indices(task.n_components)
    if pattern == CONFLICTING and conflict_specs is None:
        conflict_specs = _default_conflict_specs(task)
        if not conflict_specs:
            raise ValueError(
                f"task {task.task_id!r} has no component with a variant; "
                "a conflicting instance cannot be generated")

    holdings = assign(
        task.n_components, agent_count, pattern,
        overlap_indices=overlap_indices or (),
        conflict_specs=conflict_specs or ())

    os.makedirs(out_dir, exist_ok=True)
    prompts_dir = os.path.join(out_dir, "prompts")
    os.makedirs(prompts_dir, exist_ok=True)

    agents = []
    for i, held in enumerate(holdings):
        agent_id = f"agent-{i + 1}"
        prompt = render_prompt(task, agent_count, held)
        with open(os.path.join(prompts_dir, f"{agent_id}.txt"),
                  "w", encoding="utf-8") as fh:
            fh.write(prompt)
        agents.append({
            "agent_id": agent_id,
            "prompt_file": f"prompts/{agent_id}.txt",
            "components": [
                {"label": task.components[h.component_index].label,
                 "index": h.component_index,
                 "variant": h.variant}
                for h in held
            ],
        })

    manifest = {
        "task_id": task.task_id,
        "function_name": task.function_name,
        "solution_path": task.solution_path,
        "agent_count": agent_count,
        "pattern": pattern,
        "n_components": task.n_components,
        "verifier_path": task.verifier_path,
        "reference_solution_path": task.reference_solution_path,
        "agents": agents,
    }
    with open(os.path.join(out_dir, "instance.json"),
              "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
    return manifest
