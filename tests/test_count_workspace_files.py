"""Tests for the end-of-run workspace counting rule in
scripts/count_workspace_files.py.

The rule: regular files under workspace/, recursive, excluding __pycache__/
directories and *.pyc bytecode (verifier post-hoc artefacts). Nested agent
files count once each; directories are not counted as items.
"""

from __future__ import annotations

import importlib.util
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_PATH = os.path.join(REPO_ROOT, "scripts", "count_workspace_files.py")


def _import():
    spec = importlib.util.spec_from_file_location("count_workspace_files",
                                                  SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, REPO_ROOT)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def test_excludes_pycache_and_pyc(tmp_path):
    m = _import()
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "solution.py").write_text("x = 1\n")
    # verifier post-hoc bytecode: a __pycache__ dir with a .pyc -> excluded
    pyc = ws / "__pycache__"
    pyc.mkdir()
    (pyc / "solution.cpython-314.pyc").write_bytes(b"\x00")
    assert m.count_workspace_files(str(ws)) == 1


def test_counts_nested_agent_files_once(tmp_path):
    m = _import()
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "solution.py").write_text("x = 1\n")
    (ws / "spec_validation.md").write_text("# spec\n")
    sub = ws / "spec_parts"          # agent-created subdirectory with a file
    sub.mkdir()
    (sub / "part_a.md").write_text("a\n")
    # the subdirectory itself is not an item; its file is counted -> 3 files
    assert m.count_workspace_files(str(ws)) == 3


def test_forbidden_like_single_deliverable(tmp_path):
    m = _import()
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "solution.py").write_text("x = 1\n")
    assert m.count_workspace_files(str(ws)) == 1


def test_missing_workspace_returns_none(tmp_path):
    m = _import()
    assert m.count_workspace_files(str(tmp_path / "nope")) is None


def test_parse_run_id():
    m = _import()
    p = m.parse_run_id(
        "family-1-process_orders-clean-a8-peer-forbidden-r03")
    assert p["agent_count"] == 8
    assert p["topology"] == "peer"
    assert p["artefact_policy"] == "forbidden"
    assert m.parse_run_id("not-a-run") is None
