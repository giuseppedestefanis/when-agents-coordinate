"""Tests for the experiment runner (infrastructure component 4).

Cover the configuration matrix, the per-run working directory setup, the
verifier, the ledger, and an end-to-end run with a fake launcher that stands
in for the Claude Code invocation.
"""

import json
import os

import pytest

from agent_comms.runner import (
    Cell, ExperimentRunner, Ledger, LaunchOutcome, RunResult, STATUS_ERROR,
    STATUS_OK, enumerate_cells, expand, family_1_specs,
    is_degenerate, lock_workspace_for_strict_forbidden, prepare_run, run_id,
    run_verifier,
)
from agent_comms.runner.workspace import apply_policy, mcp_config
from agent_comms.task_generator import get_task

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# --- fixtures and helpers --------------------------------------------------

def _reference_solution():
    """Return the text of the process_orders reference solution."""
    path = os.path.join(REPO_ROOT, "tasks/family-1/instance-1/solution.py")
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


_BROKEN_SOLUTION = "def process_orders(orders, config):\n    return None\n"


def _session_line(agent_id):
    """One assistant turn that writes solution.py, as a session JSONL line."""
    obj = {
        "type": "assistant",
        "uuid": f"{agent_id}-t1",
        "timestamp": "2026-05-22T10:00:00.000000+00:00",
        "isSidechain": False,
        "message": {
            "model": "claude-opus-4-7",
            "usage": {"input_tokens": 100, "output_tokens": 40},
            "content": [{
                "type": "tool_use", "id": f"{agent_id}-c1", "name": "Write",
                "input": {"file_path": "solution.py", "content": "x = 1\n"},
            }],
        },
    }
    return json.dumps(obj) + "\n"


def make_launcher(solution_text, error=None):
    """Return a fake launcher that simulates the agents of a run."""

    def launcher(layout, spec):
        if error is not None:
            return LaunchOutcome(error=error)
        with open(layout.solution_path, "w", encoding="utf-8") as fh:
            fh.write(solution_text)
        sessions = []
        for agent in layout.agents:
            path = os.path.join(
                layout.sessions_dir, f"{agent.agent_id}.jsonl")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(_session_line(agent.agent_id))
            sessions.append({"agent_id": agent.agent_id, "path": path})
        return LaunchOutcome(sessions=sessions, wall_time_s=1.5)

    return launcher


def _spec(cell, pattern="clean", rep=1):
    return expand(
        [cell], "family-1", "process_orders", pattern, 1, start=rep)[0]


# --- the configuration matrix ----------------------------------------------

def test_cell_rejects_invalid_values():
    with pytest.raises(ValueError):
        Cell(3, "peer", "allowed")
    with pytest.raises(ValueError):
        Cell(2, "mesh", "allowed")
    with pytest.raises(ValueError):
        Cell(2, "peer", "optional")


def test_cell_label():
    assert Cell(4, "orchestrator", "allowed").label == "a4-orchestrator-allowed"


def test_is_degenerate():
    assert is_degenerate(Cell(1, "peer", "allowed"))
    assert is_degenerate(Cell(1, "solo", "mandatory"))
    assert not is_degenerate(Cell(1, "solo", "allowed"))
    assert not is_degenerate(Cell(2, "peer", "mandatory"))


def test_enumerate_cells_has_no_degenerate_cells():
    cells = enumerate_cells()
    assert len(cells) == 31
    assert all(not is_degenerate(c) for c in cells)


def test_run_id_is_deterministic_and_safe():
    cell = Cell(4, "peer", "forbidden")
    rid = run_id("family-1", "process_orders", "clean", cell, 7)
    assert rid == "family-1-process_orders-clean-a4-peer-forbidden-r07"
    assert " " not in rid


def test_expand_produces_one_spec_per_repetition():
    cells = [Cell(2, "peer", "allowed"), Cell(4, "peer", "allowed")]
    specs = expand(cells, "family-1", "process_orders", "clean", 5)
    assert len(specs) == 10
    assert len({s.run_id for s in specs}) == 10


def test_family_1_specs_gives_solo_cells_one_pattern():
    specs = family_1_specs(repetitions=1)
    solo = [s for s in specs if s.cell.agent_count == 1]
    assert solo and all(s.pattern == "clean" for s in solo)
    multi = [s for s in specs if s.cell.agent_count > 1]
    assert {s.pattern for s in multi} == {
        "clean", "overlapping", "conflicting"}


def test_family_2_main_matrix_specs_85_cells_at_n10():
    """The Family 2 main matrix is the same 85-cell shape as Family 1.

    Locked by `memory/experiments/family-2-full/matrix.md`: 85 cells x
    N=10 = 850 runs on `summarise_transactions`, identical axes to
    Family 1 to support the cross-family comparison.
    """
    from agent_comms.runner import family_2_main_matrix_specs
    specs = family_2_main_matrix_specs(repetitions=10)
    assert len(specs) == 850
    assert all(s.family == "family-2" for s in specs)
    assert all(s.task_id == "summarise_transactions" for s in specs)
    # Solo cells emit only the clean pattern.
    solo = [s for s in specs if s.cell.agent_count == 1]
    assert solo and all(s.pattern == "clean" for s in solo)
    # Multi-agent cells emit all three patterns.
    multi = [s for s in specs if s.cell.agent_count > 1]
    assert {s.pattern for s in multi} == {
        "clean", "overlapping", "conflicting"}


# --- per-run working directory setup ---------------------------------------

def test_apply_policy():
    base = "Implement the function."
    assert apply_policy(base, "allowed", "solution.py") == base
    forbidden = apply_policy(base, "forbidden", "solution.py")
    assert "only file" in forbidden and "solution.py" in forbidden
    mandatory = apply_policy(base, "mandatory", "solution.py")
    assert "must be written to a shared file" in mandatory


def test_apply_policy_family_2_forbidden_names_pipeline_and_steps():
    """Family 2's forbidden clause talks about deliverable files (plural)
    and names pipeline.py without leaking the chain length."""
    base = "Implement your step."
    forbidden = apply_policy(
        base, "forbidden", "pipeline.py", family="family-2")
    assert "deliverable files" in forbidden
    assert "pipeline.py" in forbidden
    assert "each agent's step file" in forbidden
    # Must NOT leak the count of chain steps.
    assert "four" not in forbidden.lower()
    assert "eight" not in forbidden.lower()


def test_apply_policy_family_2_mandatory_is_same_as_family_1():
    """The mandatory clause is family-independent."""
    base = "Implement your step."
    mandatory_1 = apply_policy(
        base, "mandatory", "solution.py", family="family-1")
    mandatory_2 = apply_policy(
        base, "mandatory", "pipeline.py", family="family-2")
    assert mandatory_1 == mandatory_2


def test_mcp_config_wires_the_message_protocol():
    cfg = mcp_config("agent-1", "/run/messages.jsonl", "run-x",
                      ["agent-1", "agent-2"], repo_root="/repo")
    server = cfg["mcpServers"]["agent-comms"]
    assert server["args"] == ["-m", "agent_comms.message_protocol.server"]
    assert server["env"]["AGENT_COMMS_SELF"] == "agent-1"
    assert server["env"]["AGENT_COMMS_LOG"] == "/run/messages.jsonl"
    assert server["env"]["AGENT_COMMS_ROSTER"] == "agent-1,agent-2"
    # repo_root goes on PYTHONPATH so the spawned server can import the package
    assert server["env"]["PYTHONPATH"] == "/repo"


def test_prepare_run_multi_agent(tmp_path):
    task = get_task("process_orders")
    spec = _spec(Cell(2, "peer", "forbidden"))
    layout = prepare_run(
        spec, task, str(tmp_path / "runs"), repo_root=REPO_ROOT)

    for directory in (layout.instance_dir, layout.workspace_dir,
                      layout.sessions_dir, layout.datasets_dir):
        assert os.path.isdir(directory)
    assert os.path.exists(os.path.join(layout.instance_dir, "instance.json"))
    assert os.path.exists(layout.verifier_path)
    assert os.path.exists(layout.spec_path)
    assert len(layout.agents) == 2
    for agent in layout.agents:
        assert os.path.exists(agent.prompt_path)
        assert os.path.exists(agent.mcp_config_path)
        with open(agent.prompt_path, "r", encoding="utf-8") as fh:
            assert "only file" in fh.read()  # forbidden policy clause applied
    with open(layout.agents[0].mcp_config_path, "r", encoding="utf-8") as fh:
        server = json.load(fh)["mcpServers"]["agent-comms"]
    assert server["env"]["PYTHONPATH"] == REPO_ROOT


def test_prepare_run_solo_has_no_mcp_config(tmp_path):
    task = get_task("process_orders")
    spec = _spec(Cell(1, "solo", "allowed"))
    layout = prepare_run(
        spec, task, str(tmp_path / "runs"), repo_root=REPO_ROOT)
    assert len(layout.agents) == 1
    assert layout.agents[0].mcp_config_path is None


def test_prepare_run_family_2_full_path(tmp_path):
    """End-to-end prepare_run for a Family 2 spec.

    Confirms the verifier is copied from the Family 2 location, the
    prompts use the chain framing rather than the single-function
    framing, the forbidden-policy clause uses the Family 2 plural
    wording, and the manifest carries the Family 2 task identity.
    """
    from agent_comms.runner import expand
    task = get_task("summarise_transactions")
    spec = expand(
        [Cell(4, "peer", "forbidden")], "family-2",
        "summarise_transactions", "clean", 1)[0]
    layout = prepare_run(
        spec, task, str(tmp_path / "runs"), repo_root=REPO_ROOT)

    # Verifier copied from the Family 2 path.
    assert os.path.exists(layout.verifier_path)
    with open(layout.verifier_path, "r", encoding="utf-8") as fh:
        assert "summarise_transactions" in fh.read()

    # Four agents, each with a Family 2 prompt.
    assert len(layout.agents) == 4
    prompt_1 = open(layout.agents[0].prompt_path).read()
    assert "chain of step functions" in prompt_1
    assert "pipeline.py" in prompt_1
    assert "`parse.py`" in prompt_1  # agent 1 holds the parse step
    # Family 2 forbidden clause: plural, names pipeline.py.
    assert "deliverable files" in prompt_1
    assert "each agent's step file" in prompt_1


def test_prepare_run_family_2_conflict_distributes_strict_variant(tmp_path):
    """A Family 2 conflicting spec routes the strict validate variant to
    one of the agents, producing the B2 conflict on the validate step."""
    from agent_comms.runner import expand
    task = get_task("summarise_transactions")
    spec = expand(
        [Cell(4, "peer", "allowed")], "family-2",
        "summarise_transactions", "conflicting", 1)[0]
    layout = prepare_run(
        spec, task, str(tmp_path / "runs"), repo_root=REPO_ROOT)
    joined = "\n".join(
        open(agent.prompt_path).read() for agent in layout.agents)
    assert "strictly greater than zero" in joined
    assert "greater than or equal to zero" in joined


def test_lock_workspace_for_strict_forbidden_locks_creation(tmp_path):
    task = get_task("process_orders")
    spec = _spec(Cell(2, "peer", "forbidden"))
    layout = prepare_run(
        spec, task, str(tmp_path / "runs"), repo_root=REPO_ROOT)
    lock_workspace_for_strict_forbidden(layout)

    # solution.py exists and is writable: the agent overwrites it later.
    assert os.path.exists(layout.solution_path)
    with open(layout.solution_path, "w", encoding="utf-8") as fh:
        fh.write("def f(): pass\n")

    # The workspace directory refuses creation of any other file.
    other = os.path.join(layout.workspace_dir, "scratch.txt")
    with pytest.raises(PermissionError):
        with open(other, "w", encoding="utf-8") as fh:
            fh.write("x")


def test_runner_calls_post_prepare_hook(tmp_path):
    task = get_task("process_orders")
    calls = []

    def hook(layout, spec):
        calls.append((layout.run_id, spec.run_id))

    runner = ExperimentRunner(
        str(tmp_path / "exp"), make_launcher(_reference_solution()),
        repo_root=REPO_ROOT, post_prepare=hook)
    spec = _spec(Cell(2, "peer", "allowed"))
    runner.run_one(spec, get_task("process_orders"))
    assert calls == [(spec.run_id, spec.run_id)]


def test_prepare_run_orchestrator_assigns_coordinator(tmp_path):
    task = get_task("process_orders")
    spec = _spec(Cell(4, "orchestrator", "allowed"))
    layout = prepare_run(
        spec, task, str(tmp_path / "runs"), repo_root=REPO_ROOT)
    # Exactly the first agent is given the coordinator role.
    with open(layout.agents[0].prompt_path, encoding="utf-8") as fh:
        assert "coordinator" in fh.read().lower()
    with open(layout.agents[1].prompt_path, encoding="utf-8") as fh:
        assert "coordinator" not in fh.read().lower()


# --- the verifier ----------------------------------------------------------

def test_run_verifier_passes_on_the_reference_solution(tmp_path):
    task = get_task("process_orders")
    spec = _spec(Cell(2, "peer", "allowed"))
    layout = prepare_run(
        spec, task, str(tmp_path / "runs"), repo_root=REPO_ROOT)
    with open(layout.solution_path, "w", encoding="utf-8") as fh:
        fh.write(_reference_solution())
    verdict = run_verifier(layout)
    assert verdict.success
    assert verdict.passed > 0 and verdict.failed == 0


def test_run_verifier_fails_on_a_broken_solution(tmp_path):
    task = get_task("process_orders")
    spec = _spec(Cell(2, "peer", "allowed"))
    layout = prepare_run(
        spec, task, str(tmp_path / "runs"), repo_root=REPO_ROOT)
    with open(layout.solution_path, "w", encoding="utf-8") as fh:
        fh.write(_BROKEN_SOLUTION)
    verdict = run_verifier(layout)
    assert not verdict.success
    assert verdict.failed + verdict.errors > 0


def test_run_verifier_reports_a_missing_solution(tmp_path):
    task = get_task("process_orders")
    spec = _spec(Cell(2, "peer", "allowed"))
    layout = prepare_run(
        spec, task, str(tmp_path / "runs"), repo_root=REPO_ROOT)
    verdict = run_verifier(layout)
    assert not verdict.success
    assert "solution not produced" in verdict.error


# --- the ledger ------------------------------------------------------------

def test_ledger_records_and_resumes(tmp_path):
    path = str(tmp_path / "ledger.json")
    ledger = Ledger(path)
    spec = _spec(Cell(2, "peer", "allowed"))
    assert ledger.pending([spec]) == [spec]

    ledger.update(spec, RunResult(spec.run_id, STATUS_OK, success=True))
    assert ledger.is_complete(spec.run_id)
    assert ledger.pending([spec]) == []

    reloaded = Ledger(path)
    assert reloaded.is_complete(spec.run_id)


def test_ledger_error_run_stays_pending(tmp_path):
    ledger = Ledger(str(tmp_path / "ledger.json"))
    spec = _spec(Cell(2, "peer", "allowed"))
    ledger.update(spec, RunResult(spec.run_id, STATUS_ERROR, error="boom"))
    assert not ledger.is_complete(spec.run_id)
    assert ledger.pending([spec]) == [spec]


def test_ledger_summary(tmp_path):
    ledger = Ledger(str(tmp_path / "ledger.json"))
    s1 = _spec(Cell(2, "peer", "allowed"), rep=1)
    s2 = _spec(Cell(2, "peer", "allowed"), rep=2)
    s3 = _spec(Cell(2, "peer", "allowed"), rep=3)
    ledger.update(s1, RunResult(s1.run_id, STATUS_OK, success=True))
    ledger.update(s2, RunResult(s2.run_id, STATUS_OK, success=False))
    ledger.update(s3, RunResult(s3.run_id, STATUS_ERROR, error="boom"))
    summary = ledger.summary()
    assert summary == {
        "runs": 3, "ok": 2, "error": 1, "succeeded": 1, "failed": 1}


# --- end-to-end orchestration ----------------------------------------------

def test_run_one_success(tmp_path):
    runner = ExperimentRunner(
        str(tmp_path / "exp"), make_launcher(_reference_solution()),
        repo_root=REPO_ROOT)
    spec = _spec(Cell(2, "peer", "allowed"))
    result = runner.run_one(spec, get_task("process_orders"))

    assert result.status == STATUS_OK
    assert result.success is True
    assert result.tests_passed > 0 and result.tests_failed == 0
    assert os.path.exists(os.path.join(result.run_dir, "result.json"))
    assert os.path.exists(
        os.path.join(result.run_dir, "datasets", "edges.csv"))
    assert runner.ledger.is_complete(spec.run_id)


def test_run_one_populates_role_names_in_parsed_edges_family_2(tmp_path):
    """Stage 3 of the 2026-05-30 parser-convention change: the runner
    must populate run_record.role_names from the task so a message
    addressed to a step role (e.g. `to=parse`) is classified as
    TARGET_KIND_ROLE in the parsed edges.csv, not TARGET_KIND_UNKNOWN.
    """
    import csv
    from agent_comms.runner import expand

    # A fake launcher that writes the Family 2 deliverables and one
    # message addressed by role name.
    def family_2_launcher(layout, spec):
        # Minimal pipeline.py to satisfy the parser's verifier path.
        with open(os.path.join(layout.workspace_dir, "pipeline.py"),
                  "w", encoding="utf-8") as fh:
            fh.write("def summarise_transactions(records):\n    return []\n")
        # One session per agent with one Write tool call each.
        sessions = []
        for agent in layout.agents:
            path = os.path.join(
                layout.sessions_dir, f"{agent.agent_id}.jsonl")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(_session_line(agent.agent_id))
            sessions.append({"agent_id": agent.agent_id, "path": path})
        # One message addressed by role name.
        message_log_path = layout.message_log
        with open(message_log_path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "event": "message", "seq": 0,
                "from": "agent-1", "to": "parse",
                "ts": "2026-05-30T10:00:00.000Z",
                "tokens_estimate": 1, "bytes": 1,
            }) + "\n")
        return LaunchOutcome(sessions=sessions, wall_time_s=1.5)

    runner = ExperimentRunner(
        str(tmp_path / "exp"), family_2_launcher, repo_root=REPO_ROOT)
    spec = expand(
        [Cell(4, "peer", "allowed")], "family-2",
        "summarise_transactions", "clean", 1)[0]
    result = runner.run_one(spec, get_task("summarise_transactions"))
    assert result.status == STATUS_OK

    # The parsed edges.csv must classify the `to=parse` edge as role.
    edges_csv = os.path.join(result.run_dir, "datasets", "edges.csv")
    with open(edges_csv, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    message_rows = [r for r in rows if r["subtype"] == "message"]
    assert len(message_rows) == 1
    assert message_rows[0]["target"] == "parse"
    assert message_rows[0]["target_kind"] == "role"


def test_run_one_failed_verifier(tmp_path):
    runner = ExperimentRunner(
        str(tmp_path / "exp"), make_launcher(_BROKEN_SOLUTION),
        repo_root=REPO_ROOT)
    spec = _spec(Cell(2, "peer", "allowed"))
    result = runner.run_one(spec, get_task("process_orders"))
    assert result.status == STATUS_OK
    assert result.success is False


def test_run_one_launcher_error(tmp_path):
    runner = ExperimentRunner(
        str(tmp_path / "exp"), make_launcher("", error="no agent runtime"),
        repo_root=REPO_ROOT)
    spec = _spec(Cell(2, "peer", "allowed"))
    result = runner.run_one(spec, get_task("process_orders"))
    assert result.status == STATUS_ERROR
    assert result.error == "no agent runtime"


def test_run_one_launcher_raises(tmp_path):
    def bad_launcher(layout, spec):
        raise RuntimeError("crashed")

    runner = ExperimentRunner(
        str(tmp_path / "exp"), bad_launcher, repo_root=REPO_ROOT)
    spec = _spec(Cell(2, "peer", "allowed"))
    result = runner.run_one(spec, get_task("process_orders"))
    assert result.status == STATUS_ERROR
    assert "crashed" in result.error


def test_run_one_error_with_partial_sessions_skips_parser(tmp_path):
    """A launcher that errors after writing partial session files must not
    produce a per-run dataset. The dataset would otherwise carry a
    zero-or-near-zero-count row into the master CSV indistinguishable
    from a real low-activity run (the ghost-row bug, fixed 2026-05-28).
    """

    def partial_session_launcher(layout, spec):
        # Mimic a launcher that opened session files for each agent and
        # then crashed: the session files exist, but the result is an
        # error and the run never produced a solution.
        sessions = []
        for agent in layout.agents:
            path = os.path.join(
                layout.sessions_dir, f"{agent.agent_id}.jsonl")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(_session_line(agent.agent_id))
            sessions.append({"agent_id": agent.agent_id, "path": path})
        return LaunchOutcome(
            sessions=sessions, wall_time_s=2.0,
            error="agent-1 exited 1")

    runner = ExperimentRunner(
        str(tmp_path / "exp"), partial_session_launcher,
        repo_root=REPO_ROOT)
    spec = _spec(Cell(2, "peer", "allowed"))
    result = runner.run_one(spec, get_task("process_orders"))

    assert result.status == STATUS_ERROR
    # The parser was skipped because the run errored, so no dataset
    # files were written. (`prepare_run` may have created an empty
    # datasets/ directory; the contamination concern is the files
    # the parser would write inside it.) The ledger still records
    # the error verbatim, so the run state itself is not lost.
    datasets_dir = os.path.join(result.run_dir, "datasets")
    assert not os.path.exists(os.path.join(datasets_dir, "runs.csv"))
    assert not os.path.exists(os.path.join(datasets_dir, "edges.csv"))
    assert not os.path.exists(os.path.join(datasets_dir, "nodes.csv"))


def test_run_all_resumes_and_combines(tmp_path):
    runner = ExperimentRunner(
        str(tmp_path / "exp"), make_launcher(_reference_solution()),
        repo_root=REPO_ROOT)
    task = get_task("process_orders")
    specs = expand(
        [Cell(2, "peer", "allowed")], "family-1", "process_orders",
        "clean", 2)

    first = runner.run_all(specs, task)
    assert len(first) == 2
    assert os.path.exists(os.path.join(runner.master_dir, "runs.csv"))
    assert os.path.exists(os.path.join(runner.experiment_root, "ledger.csv"))

    # A second call with the same specs skips the completed runs.
    second = runner.run_all(specs, task)
    assert second == []


def test_run_all_does_not_re_run(tmp_path):
    runner = ExperimentRunner(
        str(tmp_path / "exp"), make_launcher(_reference_solution()),
        repo_root=REPO_ROOT)
    task = get_task("process_orders")
    spec = _spec(Cell(2, "peer", "allowed"))
    assert len(runner.run_all([spec], task)) == 1
    assert runner.run_all([spec], task) == []


def test_run_all_pauses_on_rate_limit_cascade(tmp_path):
    """A cascade of fast errors pauses the batch instead of marching on."""

    def fast_error_launcher(layout, spec):
        # The signature: all agents exit immediately, wall < threshold.
        return LaunchOutcome(error="agent-1 exited 1", wall_time_s=2.0)

    runner = ExperimentRunner(
        str(tmp_path / "exp"), fast_error_launcher, repo_root=REPO_ROOT)
    task = get_task("process_orders")
    specs = expand(
        [Cell(2, "peer", "allowed")], "family-1", "process_orders",
        "clean", 10)

    results = runner.run_all(specs, task)
    # Three consecutive fast errors triggers the pause; the rest is skipped.
    assert len(results) == 3
    assert all(r.status == STATUS_ERROR for r in results)
    # The ledger reflects the same: three errors recorded, seven still pending
    # for a subsequent invocation to retry.
    summary = runner.ledger.summary()
    assert summary["runs"] == 3
    assert summary["error"] == 3
    assert summary["ok"] == 0


def test_run_all_fast_error_counter_resets_on_success(tmp_path):
    """Fast errors interleaved with successes do not trip the cascade guard."""

    state = {"call": 0}

    def alternating_launcher(layout, spec):
        state["call"] += 1
        if state["call"] % 2 == 0:
            return LaunchOutcome(error="agent-1 exited 1", wall_time_s=2.0)
        # Successful run with a real session log so the verifier and parser
        # have something to consume.
        with open(layout.solution_path, "w", encoding="utf-8") as fh:
            fh.write(_reference_solution())
        sessions = []
        for agent in layout.agents:
            path = os.path.join(
                layout.sessions_dir, f"{agent.agent_id}.jsonl")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(_session_line(agent.agent_id))
            sessions.append({"agent_id": agent.agent_id, "path": path})
        return LaunchOutcome(sessions=sessions, wall_time_s=1.5)

    runner = ExperimentRunner(
        str(tmp_path / "exp"), alternating_launcher, repo_root=REPO_ROOT)
    task = get_task("process_orders")
    specs = expand(
        [Cell(2, "peer", "allowed")], "family-1", "process_orders",
        "clean", 6)

    results = runner.run_all(specs, task)
    # The alternating pattern never has three fast errors in a row, so the
    # batch runs to completion: six results returned.
    assert len(results) == 6


def test_run_all_combines_periodically(tmp_path, monkeypatch):
    """The master CSV is rebuilt every combine_every runs, not only at end."""

    combine_calls = {"n": 0}

    runner = ExperimentRunner(
        str(tmp_path / "exp"), make_launcher(_reference_solution()),
        repo_root=REPO_ROOT)
    original_combine = runner.combine

    def counting_combine():
        combine_calls["n"] += 1
        return original_combine()

    monkeypatch.setattr(runner, "combine", counting_combine)
    task = get_task("process_orders")
    specs = expand(
        [Cell(2, "peer", "allowed")], "family-1", "process_orders",
        "clean", 5)

    runner.run_all(specs, task, combine_every=2)
    # Two periodic combines after runs 2 and 4, plus one final combine,
    # equals three. With combine_every disabled there would be only one.
    assert combine_calls["n"] == 3
