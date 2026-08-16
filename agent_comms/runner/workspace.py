"""Per-run working directory setup.

prepare_run builds the isolated directory tree for one run. Every run gets its
own directory under the experiment root, named by its run_id, so that runs do
not interfere with one another (the verifier isolation question in
memory/open-questions.md).

The directory tree for a run is:

    <run_id>/
      spec.json        the RunSpec, for traceability
      instance/        the generated task instance (component 3 output)
      prompts/         per-agent prompts, with the artefact-policy clause, and
                       for orchestrator runs the coordinator clause, added
      workspace/       the shared working directory the agents act in
      sessions/        the collected Claude Code session JSONL files
      messages/        reserved; the message log sits at messages.jsonl
      messages.jsonl   the message protocol log for the run (component 1)
      mcp/             per-agent MCP server configuration files
      verifier/        the verifier, copied outside the workspace
      datasets/        the parser CSV datasets for the run (component 2)
      result.json      the RunResult

The verifier is copied into verifier/ and never placed in workspace/, so it is
not part of the deliverable tree the agents are asked to work in. Note that
this is placement rather than enforcement: the agents run as ordinary
processes with file access and are not confined to workspace/, so paths
outside it remain reachable.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field

from agent_comms.task_generator import generate_instance
from agent_comms.task_generator.distribution import CLEAN

# Artefact-policy clauses. PLAN.md's artefact policy axis is an intervention
# (RQ4): it constrains whether shared files may carry information between
# agents. The constraint is communicated to the agents by appending a clause
# to each prompt. The "allowed" policy is the unconstrained baseline and adds
# no clause. The prompts otherwise name no communication mechanism, so that
# coordination strategy stays emergent. Enforcement by tool restriction rather
# than instruction is recorded as an open question.
_FORBIDDEN_CLAUSE = """\
Constraint on shared files. The only file the team may create in the shared \
working directory is {solution_path}, the team's deliverable. Do not create \
any other shared file to carry information between agents."""

_FAMILY_2_FORBIDDEN_CLAUSE = """\
Constraint on shared files. The only files the team may create in the shared \
working directory are the team's deliverable files: each agent's step file or \
files, and {solution_path} (the pipeline file that composes them). Do not \
create any other shared file to carry information between agents."""

_MANDATORY_CLAUSE = """\
Constraint on shared files. Any information that has to pass from one agent to \
another must be written to a shared file in the working directory. Do not rely \
on any other channel to carry that information between agents."""


def apply_policy(prompt: str, artefact_policy: str, solution_path: str,
                 family: str = "family-1") -> str:
    """Return the prompt with the artefact-policy clause appended.

    `family` selects the wording of the forbidden clause: Family 1 names
    one deliverable file; Family 2 names the team's deliverable files in
    the plural (because the chain produces N step files plus pipeline.py).
    The mandatory clause is the same for both families.
    """
    if artefact_policy == "forbidden":
        if family == "family-2":
            clause = _FAMILY_2_FORBIDDEN_CLAUSE.format(
                solution_path=solution_path)
        else:
            clause = _FORBIDDEN_CLAUSE.format(solution_path=solution_path)
    elif artefact_policy == "mandatory":
        clause = _MANDATORY_CLAUSE
    else:
        return prompt
    return prompt.rstrip() + "\n\n" + clause + "\n"


# Coordinator-role clause for the orchestrator topology. PLAN.md's orchestrator
# topology is realised as designated-coordinator peers: the run is a set of
# peer sessions, and one agent's prompt assigns it the coordinator role. The
# clause names the role without dictating a communication mechanism, so the
# coordination structure that emerges is still under study.
_COORDINATOR_CLAUSE = """\
Coordination role. You are the coordinator for this team. Take responsibility \
for gathering the parts of the specification held by the other agents, for \
assembling them, and for seeing that the finished implementation is produced."""


def apply_coordinator_role(prompt: str) -> str:
    """Return the prompt with the coordinator-role clause appended."""
    return prompt.rstrip() + "\n\n" + _COORDINATOR_CLAUSE + "\n"


def lock_workspace_for_strict_forbidden(layout, spec=None) -> None:
    """Enforce the forbidden artefact policy at the filesystem level.

    The pilot showed that telling agents not to create files leaks: agents
    still create coordination files despite the prompt clause. This function
    is the enforcement variant used for the methodological ablation. It
    pre-creates the deliverable file (which the agent later overwrites) and
    makes the workspace directory non-writable. With mode 0o555, the kernel
    refuses creation, deletion or renaming of any other file in that
    directory; writes to the existing deliverable, whose own mode permits
    writes, continue to succeed. The result is a tool-restricted forbidden
    policy that can be compared against the instruction-based one.

    Designed to be passed as the post_prepare hook of ExperimentRunner. The
    spec argument is accepted for hook compatibility and is not used.
    """
    del spec  # unused; accepted for the (layout, spec) hook contract
    solution = layout.solution_path
    if not os.path.exists(solution):
        with open(solution, "w", encoding="utf-8"):
            pass
    os.chmod(solution, 0o644)
    os.chmod(layout.workspace_dir, 0o555)


def mcp_config(agent_id: str, message_log: str, run_id: str, roster,
               python: str = "python", repo_root: str | None = None) -> dict:
    """Return the MCP server configuration that wires the message protocol.

    The configuration launches one message protocol server (component 1) for
    the agent, with the environment variables that server reads. repo_root, if
    given, is placed on PYTHONPATH so that `python -m agent_comms...` resolves
    the package when the server is spawned with the run's workspace as its
    working directory.
    """
    env = {
        "AGENT_COMMS_SELF": agent_id,
        "AGENT_COMMS_LOG": message_log,
        "AGENT_COMMS_RUN": run_id,
        "AGENT_COMMS_ROSTER": ",".join(roster),
    }
    if repo_root:
        env["PYTHONPATH"] = repo_root
    return {
        "mcpServers": {
            "agent-comms": {
                "command": python,
                "args": ["-m", "agent_comms.message_protocol.server"],
                "env": env,
            }
        }
    }


@dataclass
class AgentSetup:
    """The prepared inputs for one agent of a run."""

    agent_id: str
    prompt_path: str
    mcp_config_path: str | None = None


@dataclass
class RunLayout:
    """The directory layout and prepared inputs for one run."""

    run_id: str
    run_dir: str
    solution_filename: str = "solution.py"
    manifest: dict = field(default_factory=dict)
    agents: list = field(default_factory=list)

    @property
    def instance_dir(self) -> str:
        return os.path.join(self.run_dir, "instance")

    @property
    def prompts_dir(self) -> str:
        return os.path.join(self.run_dir, "prompts")

    @property
    def workspace_dir(self) -> str:
        return os.path.join(self.run_dir, "workspace")

    @property
    def sessions_dir(self) -> str:
        return os.path.join(self.run_dir, "sessions")

    @property
    def verifier_dir(self) -> str:
        return os.path.join(self.run_dir, "verifier")

    @property
    def verifier_path(self) -> str:
        return os.path.join(self.verifier_dir, "verifier.py")

    @property
    def datasets_dir(self) -> str:
        return os.path.join(self.run_dir, "datasets")

    @property
    def mcp_dir(self) -> str:
        return os.path.join(self.run_dir, "mcp")

    @property
    def message_log(self) -> str:
        return os.path.join(self.run_dir, "messages.jsonl")

    @property
    def result_path(self) -> str:
        return os.path.join(self.run_dir, "result.json")

    @property
    def spec_path(self) -> str:
        return os.path.join(self.run_dir, "spec.json")

    @property
    def solution_path(self) -> str:
        return os.path.join(self.workspace_dir, self.solution_filename)


def _write_text(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _write_json(path: str, obj) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2)


def prepare_run(spec, task, runs_root, repo_root=None,
                python="python") -> RunLayout:
    """Build the directory tree and prepared inputs for one run.

    spec: a RunSpec.
    task: the Task from the task library that the run implements.
    runs_root: the directory under which the run directory is created.
    repo_root: the repository root, used to resolve the task's verifier path
        when it is relative. Defaults to the current working directory.
    python: the interpreter command written into the MCP configuration.

    Returns a RunLayout. The MCP configuration is written only for multi-agent
    runs. A single agent has nobody to message.
    """
    repo_root = repo_root or os.getcwd()
    run_dir = os.path.abspath(os.path.join(runs_root, spec.run_id))
    layout = RunLayout(
        run_id=spec.run_id, run_dir=run_dir,
        solution_filename=task.solution_path)

    for directory in (layout.instance_dir, layout.prompts_dir,
                       layout.workspace_dir, layout.sessions_dir,
                       layout.verifier_dir, layout.datasets_dir,
                       layout.mcp_dir):
        os.makedirs(directory, exist_ok=True)

    # A single agent holds every component, so the distribution pattern has no
    # effect; generate the instance as a clean distribution in that case.
    pattern = CLEAN if spec.cell.agent_count == 1 else spec.pattern
    manifest = generate_instance(
        task, spec.cell.agent_count, pattern, layout.instance_dir)
    layout.manifest = manifest

    roster = [agent["agent_id"] for agent in manifest["agents"]]
    multi_agent = spec.cell.agent_count > 1

    agents = []
    for index, agent in enumerate(manifest["agents"]):
        agent_id = agent["agent_id"]
        source_prompt = os.path.join(layout.instance_dir, agent["prompt_file"])
        with open(source_prompt, "r", encoding="utf-8") as fh:
            prompt = fh.read()
        # The orchestrator topology designates the first agent as coordinator.
        if (spec.cell.topology == "orchestrator"
                and spec.cell.agent_count > 1 and index == 0):
            prompt = apply_coordinator_role(prompt)
        prompt = apply_policy(
            prompt, spec.cell.artefact_policy, task.solution_path,
            family=getattr(task, "family", "family-1"))
        prompt_path = os.path.join(layout.prompts_dir, f"{agent_id}.txt")
        _write_text(prompt_path, prompt)

        mcp_config_path = None
        if multi_agent:
            mcp_config_path = os.path.join(
                layout.mcp_dir, f"{agent_id}.mcp.json")
            _write_json(mcp_config_path, mcp_config(
                agent_id, layout.message_log, spec.run_id, roster, python,
                repo_root=repo_root))

        agents.append(AgentSetup(agent_id, prompt_path, mcp_config_path))
    layout.agents = agents

    verifier_src = task.verifier_path
    if verifier_src and not os.path.isabs(verifier_src):
        verifier_src = os.path.join(repo_root, verifier_src)
    if verifier_src and os.path.exists(verifier_src):
        shutil.copyfile(verifier_src, layout.verifier_path)

    _write_json(layout.spec_path, {
        "run_id": spec.run_id,
        "family": spec.family,
        "task_id": spec.task_id,
        "pattern": spec.pattern,
        "agent_count": spec.cell.agent_count,
        "topology": spec.cell.topology,
        "artefact_policy": spec.cell.artefact_policy,
        "replication": spec.replication,
    })
    return layout
