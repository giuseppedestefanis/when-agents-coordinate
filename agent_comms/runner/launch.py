"""The production launcher: drives Claude Code for a run.

ClaudeCodeLauncher implements the launcher contract (see runner.py) by
invoking the `claude` command line in headless mode, one process per agent:

- solo: at one agent (the n=1 baseline) a single `claude` process with no
  message protocol. At two or more agents the solo label is wired identically
  to peer -- one process per agent, each with its own message protocol MCP
  server -- and serves as the second flat draw (the reliability probe); the
  no-message-protocol case is the n=1 baseline only.
- peer: one `claude` process per agent, all started together so the agents
  coordinate in real time, each with its own message protocol MCP server.
- orchestrator: realised as designated-coordinator peers. It runs exactly like
  the peer topology; the coordinator role is assigned to one agent by the
  workspace setup (a clause added to that agent's prompt), not by the launcher.

All three topologies therefore take the same launch path, one Claude Code
session per agent.

How a session log is located. Each agent process is given a fresh session id
through `claude --session-id <uuid>`. Claude Code writes the session JSONL to
~/.claude/projects/<encoded working directory>/<session id>.jsonl. The launcher
finds it by globbing for the session id, copies it into the run's sessions/
directory so the run directory is self-contained, and returns its path.

Authentication. By default the launcher runs `claude` on the Claude
subscription (plan), not on a metered API key. It removes ANTHROPIC_API_KEY and
the third-party provider variables from the environment passed to each `claude`
process, so Claude Code authenticates with the subscription credentials held in
the Claude Code credential store. The machine must therefore be signed in to
Claude Code with a Claude subscription before a run (an interactive login, or
`claude setup-token` for a long-lived token for unattended use). Pass
use_subscription=False to keep the inherited environment unchanged.

The launcher is not exercised by the test suite; build_command,
find_session_file and subscription_env are unit tested, the launch path is
checked with a fake `claude` executable, and scripts/smoke_run.py runs it
against the real `claude`.
"""

from __future__ import annotations

import errno
import glob
import os
import shutil
import signal
import subprocess
import time
import uuid

from agent_comms.runner.runner import LaunchOutcome

# Permission mode for an unattended run: the agent must write files without a
# prompt. See `claude --help` for the available modes.
DEFAULT_PERMISSION_MODE = "bypassPermissions"

# A generous default ceiling on one run's wall-clock time.
DEFAULT_TIMEOUT_S = 1800

# Environment variables that route Claude Code to a metered API key or to a
# third-party provider rather than to the Claude subscription. The launcher
# removes them so that `claude` authenticates with the Claude plan.
_API_ENV_VARS = (
    "ANTHROPIC_API_KEY",
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
    "CLAUDE_CODE_USE_FOUNDRY",
)


def subscription_env(base=None):
    """Return an environment dict that makes `claude` use the Claude plan.

    A copy of the environment (os.environ, or base if given) with the
    variables that force API-key billing or a third-party provider removed, so
    that Claude Code falls back to the Claude subscription credentials.
    ANTHROPIC_AUTH_TOKEN is left in place: `claude setup-token` stores a
    long-lived subscription token there, so removing it would discard plan
    credentials rather than API ones.
    """
    env = dict(os.environ if base is None else base)
    for name in _API_ENV_VARS:
        env.pop(name, None)
    return env


def build_command(prompt, session_id, *, claude="claude", model=None,
                  permission_mode=DEFAULT_PERMISSION_MODE,
                  mcp_config_path=None, output_format="json",
                  max_budget_usd=None):
    """Build the headless `claude` command line for one agent.

    The prompt is placed immediately after `-p`, before any variadic option,
    so that it is read as the positional prompt argument. `--mcp-config` is
    variadic and is therefore placed last.
    """
    command = [
        claude, "-p", prompt,
        "--output-format", output_format,
        "--session-id", session_id,
        "--permission-mode", permission_mode,
    ]
    if model:
        command += ["--model", model]
    if max_budget_usd is not None:
        command += ["--max-budget-usd", str(max_budget_usd)]
    if mcp_config_path:
        # --strict-mcp-config: use only this run's message protocol server,
        # ignoring any MCP servers configured elsewhere on the machine.
        command += ["--strict-mcp-config", "--mcp-config", mcp_config_path]
    return command


def find_session_file(session_id, projects_root=None):
    """Return the path to the session JSONL for a session id, or None.

    Claude Code files a session under a per-working-directory project folder.
    Globbing for the session id locates it without reconstructing the folder
    name encoding.
    """
    projects_root = projects_root or os.path.expanduser("~/.claude/projects")
    matches = glob.glob(
        os.path.join(projects_root, "*", f"{session_id}.jsonl"))
    return matches[0] if matches else None


class ClaudeCodeLauncher:
    """A launcher that runs a run's agents through the `claude` command line.

    claude: the Claude Code executable.
    model: the model identifier to pin for every agent. PLAN.md requires the
        model to be pinned for the experimental phase; pass it explicitly.
    permission_mode: the Claude Code permission mode for an unattended run.
    timeout_s: wall-clock ceiling for one run.
    max_budget_usd: optional per-agent spend cap passed to `claude`. This
        applies to API-key billing only; it has no effect on the plan.
    projects_root: where Claude Code files sessions; defaults to
        ~/.claude/projects.
    use_subscription: when True (the default), run `claude` on the Claude
        subscription by stripping the API-key and provider variables from the
        environment. Set False to keep the inherited environment.
    """

    def __init__(self, *, claude="claude", model=None,
                 permission_mode=DEFAULT_PERMISSION_MODE,
                 timeout_s=DEFAULT_TIMEOUT_S, max_budget_usd=None,
                 projects_root=None, use_subscription=True):
        self.claude = claude
        self.model = model
        self.permission_mode = permission_mode
        self.timeout_s = timeout_s
        self.max_budget_usd = max_budget_usd
        self.projects_root = projects_root
        self.use_subscription = use_subscription

    def __call__(self, layout, spec) -> LaunchOutcome:
        topology = spec.cell.topology
        if topology in ("solo", "peer", "orchestrator"):
            return self._run_agents(layout)
        return LaunchOutcome(error=f"unknown topology {topology!r}")

    def _run_agents(self, layout) -> LaunchOutcome:
        """Run every agent of the run, concurrently, and collect the sessions.

        Peer agents are started together so that they coordinate in real time.
        A single-agent run (n=1) has one agent and takes the same path; at two
        or more agents the solo label runs exactly like peer.

        Wall-clock budget is enforced cumulatively across all the agents'
        wait calls and is computed against `time.monotonic`, not `time.time`.
        Using the monotonic clock is essential because the wall budget must
        survive system clock adjustments and laptop suspend cycles; using
        the wall clock was the suspected root cause of the 2026-05-30
        4046-second anomaly in family-2-summarise_transactions-clean-a2-
        orchestrator-allowed-r03 where the launcher's wait outran the
        configured 900-second timeout.

        Each agent is started in its own process group (start_new_session)
        so that on a timeout we kill the whole group, not just the
        immediate claude process. Claude spawns the message-protocol MCP
        server as a child; if that child is stuck, killing only claude
        can leave the MCP server alive holding file descriptors and
        delaying claude's actual exit. Killing the process group is the
        belt-and-braces fix.
        """
        started = time.monotonic()
        # By default, run on the Claude subscription rather than an API key.
        env = subscription_env() if self.use_subscription else None
        running = []
        for agent in layout.agents:
            with open(agent.prompt_path, "r", encoding="utf-8") as fh:
                prompt = fh.read()
            session_id = str(uuid.uuid4())
            command = build_command(
                prompt, session_id, claude=self.claude, model=self.model,
                permission_mode=self.permission_mode,
                mcp_config_path=agent.mcp_config_path,
                max_budget_usd=self.max_budget_usd)
            log_path = os.path.join(
                layout.sessions_dir, f"{agent.agent_id}.launch.log")
            log = open(log_path, "w", encoding="utf-8")
            process = subprocess.Popen(
                command, cwd=layout.workspace_dir, stdout=log,
                stderr=subprocess.STDOUT, env=env,
                start_new_session=True)
            running.append((agent, session_id, process, log))

        errors = []
        for agent, session_id, process, log in running:
            remaining = self.timeout_s - (time.monotonic() - started)
            try:
                process.wait(timeout=max(1.0, remaining))
            except subprocess.TimeoutExpired:
                _kill_process_group(process)
                errors.append(f"{agent.agent_id} timed out")
            else:
                if process.returncode != 0:
                    errors.append(
                        f"{agent.agent_id} exited {process.returncode}")
            log.close()

        sessions = []
        for agent, session_id, process, log in running:
            source = find_session_file(session_id, self.projects_root)
            if source is None:
                errors.append(f"{agent.agent_id} session log not found")
                continue
            destination = os.path.join(
                layout.sessions_dir, f"{agent.agent_id}.jsonl")
            shutil.copyfile(source, destination)
            sessions.append(
                {"agent_id": agent.agent_id, "path": destination})

        return LaunchOutcome(
            sessions=sessions,
            wall_time_s=round(time.monotonic() - started, 3),
            error="; ".join(errors) if errors else None)


# Maximum time we wait for a killed process and its process group to be
# reaped before giving up. A SIGKILL on a normal process terminates it
# immediately; the bound exists to protect against a kernel-side stuck
# wait (D-state process, blocked syscall) that would otherwise hang the
# launcher indefinitely. Ten seconds is generous; in practice the wait
# returns in milliseconds.
_KILL_REAP_TIMEOUT_S = 10


def _kill_process_group(process) -> None:
    """Kill the process's whole group with SIGKILL, then reap it.

    Used on a timeout when the agent's claude process (and its MCP
    server child) must be terminated. The process must have been
    started with `start_new_session=True` so that its session id and
    process group id are its own pid.

    The reap step is bounded by `_KILL_REAP_TIMEOUT_S` to protect the
    launcher against the case where the kernel cannot reap the process
    promptly (a stuck syscall, an NFS hang). If the reap times out the
    launcher gives up on the process and continues; the OS will reap
    it whenever it can. The launcher's wall budget is preserved either
    way.
    """
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        # Already dead before we tried to kill it; nothing more to do.
        return
    except OSError as exc:
        if exc.errno != errno.ESRCH:
            raise
        return
    try:
        process.wait(timeout=_KILL_REAP_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        # The kernel could not reap within the bound; abandon the
        # process rather than hang the launcher.
        return
