"""Tests for the production launcher (agent_comms/runner/launch.py).

build_command and find_session_file are unit tested. The end-to-end agent run
is tested with a fake `claude` executable that writes a session file, so the
concurrent-run and session-collection path is covered without invoking the
real Claude Code or consuming API budget.
"""

import os

from agent_comms.runner import (
    Cell, ClaudeCodeLauncher, build_command, expand, find_session_file,
    prepare_run, subscription_env,
)
from agent_comms.task_generator import get_task

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# A stand-in for the `claude` executable. It reads --session-id from its
# arguments and writes a minimal session JSONL where Claude Code would. It
# exits non-zero if ANTHROPIC_API_KEY is present, so a test can confirm the
# launcher strips it and runs on the subscription.
FAKE_CLAUDE = '''#!/usr/bin/env python3
import os, sys, json
if os.environ.get("ANTHROPIC_API_KEY"):
    sys.exit(3)
args = sys.argv[1:]
sid = args[args.index("--session-id") + 1]
proj = os.path.join(os.environ["FAKE_PROJECTS"], "session-project")
os.makedirs(proj, exist_ok=True)
line = {"type": "assistant", "uuid": sid,
        "timestamp": "2026-05-22T10:00:00.000000+00:00", "isSidechain": False,
        "message": {"model": "fake",
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                    "content": []}}
with open(os.path.join(proj, sid + ".jsonl"), "w") as fh:
    fh.write(json.dumps(line) + "\\n")
sys.exit(0)
'''


def _spec(cell, pattern="clean"):
    return expand([cell], "family-1", "process_orders", pattern, 1)[0]


def test_build_command_solo():
    command = build_command("do the task", "session-1")
    assert command[:3] == ["claude", "-p", "do the task"]
    assert "--session-id" in command and "session-1" in command
    assert "--permission-mode" in command
    assert "--mcp-config" not in command


def test_build_command_with_mcp_model_and_budget():
    command = build_command(
        "p", "s", model="opus", mcp_config_path="/run/agent.mcp.json",
        max_budget_usd=3)
    assert "--model" in command and "opus" in command
    assert "--max-budget-usd" in command and "3" in command
    # --mcp-config is variadic, so it must be last
    assert command[-2:] == ["--mcp-config", "/run/agent.mcp.json"]
    assert "--strict-mcp-config" in command


def test_find_session_file(tmp_path):
    project = tmp_path / "some-project"
    project.mkdir()
    session = project / "abc123.jsonl"
    session.write_text("{}\n", encoding="utf-8")
    assert find_session_file(
        "abc123", projects_root=str(tmp_path)) == str(session)
    assert find_session_file("missing", projects_root=str(tmp_path)) is None


def test_subscription_env_strips_the_api_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("CLAUDE_CODE_USE_BEDROCK", "1")
    monkeypatch.setenv("PATH", "/usr/bin")
    env = subscription_env()
    assert "ANTHROPIC_API_KEY" not in env
    assert "CLAUDE_CODE_USE_BEDROCK" not in env
    assert env["PATH"] == "/usr/bin"  # unrelated variables are preserved


def _run_with_fake_claude(tmp_path, monkeypatch, cell):
    """Run a cell through the launcher with the fake `claude` executable."""
    projects = tmp_path / "projects"
    projects.mkdir()
    fake = tmp_path / "fake-claude"
    fake.write_text(FAKE_CLAUDE, encoding="utf-8")
    fake.chmod(0o755)
    monkeypatch.setenv("FAKE_PROJECTS", str(projects))
    # The launcher must strip this so the fake `claude` does not exit 3.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-be-stripped")

    spec = _spec(cell)
    layout = prepare_run(
        spec, get_task("process_orders"), str(tmp_path / "runs"),
        repo_root=REPO_ROOT)
    launcher = ClaudeCodeLauncher(
        claude=str(fake), projects_root=str(projects))
    return launcher(layout, spec), layout


def test_launcher_runs_peer_agents_and_collects_sessions(
        tmp_path, monkeypatch):
    outcome, layout = _run_with_fake_claude(
        tmp_path, monkeypatch, Cell(2, "peer", "allowed"))
    assert outcome.error is None
    assert len(outcome.sessions) == 2
    for session in outcome.sessions:
        assert os.path.exists(session["path"])
        assert session["path"].startswith(layout.sessions_dir)


def test_launcher_runs_orchestrator_like_peer(tmp_path, monkeypatch):
    # The orchestrator topology takes the same launch path as peer.
    outcome, _ = _run_with_fake_claude(
        tmp_path, monkeypatch, Cell(2, "orchestrator", "allowed"))
    assert outcome.error is None
    assert len(outcome.sessions) == 2


# A fake `claude` that hangs forever. Used to verify the launcher's
# wall-clock budget is enforced even when the subprocess does not exit
# on its own. Sleeps for an absurd duration; the launcher's timeout
# must fire and kill the process group regardless.
HANGING_CLAUDE = '''#!/usr/bin/env python3
import time
time.sleep(3600)
'''


def test_launcher_bounds_wall_time_on_hanging_subprocess(
        tmp_path, monkeypatch):
    """The launcher must enforce its timeout_s budget even when an
    agent subprocess hangs without exiting. Regression test for the
    2026-05-30 4046-second anomaly. timeout_s here is 2 seconds; we
    assert the launcher returns within 30 seconds with a timeout
    error, not after the subprocess's 3600-second sleep."""
    projects = tmp_path / "projects"
    projects.mkdir()
    fake = tmp_path / "hanging-claude"
    fake.write_text(HANGING_CLAUDE, encoding="utf-8")
    fake.chmod(0o755)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-be-stripped")

    spec = _spec(Cell(2, "peer", "allowed"))
    layout = prepare_run(
        spec, get_task("process_orders"), str(tmp_path / "runs"),
        repo_root=REPO_ROOT)
    launcher = ClaudeCodeLauncher(
        claude=str(fake), projects_root=str(projects), timeout_s=2)

    import time as _time
    started = _time.monotonic()
    outcome = launcher(layout, spec)
    elapsed = _time.monotonic() - started

    # The launcher must return well within the subprocess's 3600s sleep.
    # Budget: 2s timeout per agent + small overhead for kill.
    assert elapsed < 30, f"launcher took {elapsed:.1f}s; should be < 30s"
    assert outcome.wall_time_s < 30
    # Both agents should be reported as timed out.
    assert outcome.error is not None
    assert "timed out" in outcome.error
