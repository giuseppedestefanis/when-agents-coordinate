"""Tests for the ghost-row filter in scripts/analyse_family1_full.py.

The filter is the second half of the 2026-05-28 ghost-row fix
(runner.py is the first half): historical contamination in runs.csv
from errored runs that left partial datasets is rejected by
cross-checking against the ledger's `status == "ok"` set before
cell statistics are computed.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_PATH = os.path.join(REPO_ROOT, "scripts", "analyse_family1_full.py")


def _import_analyse():
    """Load scripts/analyse_family1_full.py as a module."""
    spec = importlib.util.spec_from_file_location("analyse_family1_full",
                                                  SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, REPO_ROOT)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def _write_runs_csv(path, rows):
    """Write a minimal runs.csv mirroring the parser's output schema."""
    import csv
    fields = [
        "run_id", "family", "instance", "agent_count", "topology",
        "artefact_policy", "success", "completion_time_s",
        "total_input_tokens", "total_output_tokens", "n_nodes", "n_edges",
        "n_agent_nodes", "n_file_nodes", "n_agent_to_agent",
        "n_agent_to_file", "n_file_to_agent",
    ]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in rows:
            base = {k: "" for k in fields}
            base.update(row)
            w.writerow(base)


def _real_row(run_id, success=True):
    """A plausible row produced by a real successful run."""
    return {
        "run_id": run_id, "family": "family-1", "instance": "process_orders",
        "agent_count": "2", "topology": "peer", "artefact_policy": "allowed",
        "success": "True" if success else "False",
        "completion_time_s": "120.5",
        "total_input_tokens": "5000", "total_output_tokens": "1500",
        "n_nodes": "3", "n_edges": "12", "n_agent_nodes": "2",
        "n_file_nodes": "1", "n_agent_to_agent": "4.0",
        "n_agent_to_file": "3.0", "n_file_to_agent": "5.0",
    }


def _ghost_row(run_id):
    """A zero-or-near-zero-count row of the shape a partial parse can leave."""
    return {
        "run_id": run_id, "family": "family-1", "instance": "process_orders",
        "agent_count": "2", "topology": "peer", "artefact_policy": "allowed",
        "success": "False", "completion_time_s": "2.1",
        "total_input_tokens": "0", "total_output_tokens": "0",
        "n_nodes": "0", "n_edges": "0", "n_agent_nodes": "0",
        "n_file_nodes": "0", "n_agent_to_agent": "0.0",
        "n_agent_to_file": "0.0", "n_file_to_agent": "0.0",
    }


def test_load_ok_run_ids_returns_only_ok(tmp_path):
    module = _import_analyse()
    ledger = {
        "family-1-process_orders-clean-a2-peer-allowed-r01":
            {"run_id": "family-1-process_orders-clean-a2-peer-allowed-r01",
             "status": "ok"},
        "family-1-process_orders-clean-a2-peer-allowed-r02":
            {"run_id": "family-1-process_orders-clean-a2-peer-allowed-r02",
             "status": "error"},
        "family-1-process_orders-clean-a2-peer-allowed-r03":
            {"run_id": "family-1-process_orders-clean-a2-peer-allowed-r03",
             "status": "ok"},
    }
    ledger_path = tmp_path / "ledger.json"
    ledger_path.write_text(json.dumps(ledger))

    ok_ids = module.load_ok_run_ids(str(ledger_path))
    assert ok_ids == {
        "family-1-process_orders-clean-a2-peer-allowed-r01",
        "family-1-process_orders-clean-a2-peer-allowed-r03",
    }


def test_load_ok_run_ids_missing_ledger_returns_empty(tmp_path):
    module = _import_analyse()
    assert module.load_ok_run_ids(str(tmp_path / "nope.json")) == set()


def test_load_runs_drops_ghost_rows(tmp_path):
    module = _import_analyse()
    runs_csv = tmp_path / "runs.csv"
    real_id = "family-1-process_orders-clean-a2-peer-allowed-r01"
    ghost_id = "family-1-process_orders-clean-a2-peer-allowed-r02"
    _write_runs_csv(
        str(runs_csv),
        [_real_row(real_id), _ghost_row(ghost_id)],
    )

    rows, dropped = module.load_runs(str(runs_csv), ok_run_ids={real_id})
    assert dropped == 1
    assert len(rows) == 1
    assert rows[0]["run_id"] == real_id


def test_load_runs_no_ledger_keeps_every_row(tmp_path):
    """Empty ok set disables the filter (fall-back behaviour)."""
    module = _import_analyse()
    runs_csv = tmp_path / "runs.csv"
    _write_runs_csv(
        str(runs_csv),
        [
            _real_row("family-1-process_orders-clean-a2-peer-allowed-r01"),
            _ghost_row("family-1-process_orders-clean-a2-peer-allowed-r02"),
        ],
    )

    rows, dropped = module.load_runs(str(runs_csv), ok_run_ids=set())
    assert dropped == 0
    assert len(rows) == 2


def test_load_runs_drops_rows_unknown_to_ledger(tmp_path):
    """A run_id present in runs.csv but absent from the ledger ok-set
    is treated as a ghost row even if it looks complete on paper."""
    module = _import_analyse()
    runs_csv = tmp_path / "runs.csv"
    _write_runs_csv(
        str(runs_csv),
        [
            _real_row("family-1-process_orders-clean-a2-peer-allowed-r01"),
            _real_row("family-1-process_orders-clean-a2-peer-allowed-r99"),
        ],
    )

    rows, dropped = module.load_runs(
        str(runs_csv),
        ok_run_ids={"family-1-process_orders-clean-a2-peer-allowed-r01"},
    )
    assert dropped == 1
    assert len(rows) == 1
    assert rows[0]["run_id"].endswith("r01")
