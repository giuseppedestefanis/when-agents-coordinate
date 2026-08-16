"""Task generator (infrastructure component 3).

Produces runnable task instances for a study run from a structured task
definition and a set of parameters: agent count and distribution pattern
(clean, overlapping, conflicting). The component count is a property of the
task taken from the task library.

Family 1 begins as the hand-written set in tasks/family-1/. This generator
operates on a structured library of those tasks: it computes the
agent-to-component assignment and renders the per-agent prompts, so that an
instance can be produced for any agent count and distribution pattern without
hand-writing it. Generating novel component specifications from nothing is out
of scope for this version and is noted in memory/open-questions.md.

Public entry points: generate_instance, assign, and the task library.

Modules:
- model: the task data model (Component, Task).
- distribution: the agent-to-component assignment algorithm.
- instance: prompt rendering and writing a run-ready instance directory.
- library: the structured task library (currently the process_orders task).
"""

from agent_comms.task_generator.distribution import (
    CLEAN, CONFLICTING, OVERLAPPING, PATTERNS, Holding, assign,
    clean_partition,
)
from agent_comms.task_generator.instance import generate_instance, render_prompt
from agent_comms.task_generator.library import TASKS, get_task
from agent_comms.task_generator.model import Component, Task

__all__ = [
    "generate_instance", "render_prompt", "assign", "clean_partition",
    "Holding", "Component", "Task", "get_task", "TASKS",
    "CLEAN", "OVERLAPPING", "CONFLICTING", "PATTERNS",
]
