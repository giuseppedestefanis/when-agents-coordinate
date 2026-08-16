"""The experiment ledger.

The ledger is a JSON file at the experiment root recording every run that has
been executed: its configuration, its status and its outcome. It makes the
experiment resumable. A controller that stops part way through can be
restarted and will skip the runs already completed.

A run is treated as complete, and not re-run, once it has a recorded status of
"ok". A run recorded as "error" is left pending, so that a restart retries it.
"""

from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone

from agent_comms.runner.model import STATUS_OK

_CSV_FIELDS = [
    "run_id", "family", "task_id", "pattern", "agent_count", "topology",
    "artefact_policy", "replication", "status", "success", "tests_passed",
    "tests_failed", "tests_errors", "wall_time_s", "error", "run_dir",
    "updated_at",
]


class Ledger:
    """A resumable record of executed runs, backed by a JSON file."""

    def __init__(self, path: str):
        self.path = path
        self.records: dict = {}
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as fh:
                self.records = json.load(fh)

    def is_complete(self, run_id: str) -> bool:
        """Return True if the run has been executed with status ok."""
        record = self.records.get(run_id)
        return record is not None and record.get("status") == STATUS_OK

    def pending(self, specs):
        """Return the specs that are not yet complete, in input order."""
        return [s for s in specs if not self.is_complete(s.run_id)]

    def update(self, spec, result) -> None:
        """Record the result of a run and persist the ledger."""
        self.records[spec.run_id] = {
            "run_id": spec.run_id,
            "family": spec.family,
            "task_id": spec.task_id,
            "pattern": spec.pattern,
            "agent_count": spec.cell.agent_count,
            "topology": spec.cell.topology,
            "artefact_policy": spec.cell.artefact_policy,
            "replication": spec.replication,
            "status": result.status,
            "success": result.success,
            "tests_passed": result.tests_passed,
            "tests_failed": result.tests_failed,
            "tests_errors": result.tests_errors,
            "wall_time_s": result.wall_time_s,
            "error": result.error,
            "run_dir": result.run_dir,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self.save()

    def save(self) -> None:
        """Write the ledger to its JSON file."""
        parent = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(parent, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(self.records, fh, indent=2, sort_keys=True)

    def summary(self) -> dict:
        """Return aggregate counts over the recorded runs."""
        records = list(self.records.values())
        ok = [r for r in records if r.get("status") == STATUS_OK]
        return {
            "runs": len(records),
            "ok": len(ok),
            "error": len(records) - len(ok),
            "succeeded": sum(1 for r in ok if r.get("success")),
            "failed": sum(1 for r in ok if not r.get("success")),
        }

    def write_csv(self, path: str) -> str:
        """Write the ledger as a flat CSV, one row per run."""
        with open(path, "w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(
                fh, fieldnames=_CSV_FIELDS, extrasaction="ignore")
            writer.writeheader()
            for run_id in sorted(self.records):
                writer.writerow(self.records[run_id])
        return path
