#!/usr/bin/env python3
"""Family 1 full schedule, preliminary analysis pipeline.

Applies the pre-registered analysis plan in
`memory/experiments/family-1-full/analysis-plan.md`. Reads the runs.csv
written by the parser, builds per-cell-and-pattern summaries, applies
the top-up decision rule and writes the report to
`memory/experiments/family-1-full/preliminary.md`. The script also
prints a compact summary to stdout.

The rule is deliberately fixed:

    A (cell, pattern) is flagged for top-up to N = 20 if EITHER
      * the Wilson 95% interval for its success rate has width > 0.5
        (worst at p = 0.5; falls below 0.5 outside p ~ 0.2 or p ~ 0.8),
      * the coefficient of variation of any of n_agent_to_agent,
        n_agent_to_file, n_file_to_agent exceeds 0.5 (sixteen per
        cent relative standard error of the cell mean at N = 10).

Cells whose mean for a metric is zero are excluded from the CV check
for that metric (CV is undefined). They are still subject to the
outcome rule.

The thresholds (0.5 CI width; 0.5 CV) are part of the analysis plan
and may not be tuned to data without recording the change there with
a reason. Run this script repeatedly as the batch progresses; it will
read whatever is currently in runs.csv and the ledger.

Ghost-row filter: rows in runs.csv whose run_id does not appear with
status="ok" in the ledger are dropped before cell statistics are
computed. The runner's _finish step, after 2026-05-28, no longer
calls the parser on STATUS_ERROR results, so new ghost rows should
not appear; this filter is a defensive check for any historical
ghost rows that landed in runs.csv before the runner fix.

Usage::

    .venv/bin/python scripts/analyse_family1_full.py
    .venv/bin/python scripts/analyse_family1_full.py \\
        --experiment-root data/family-1-full
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import math
import os
import re
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_comms.parser.datasets import combine_datasets

RUN_RE = re.compile(
    r"^family-1-(?P<task>[a-z_]+)-(?P<pattern>clean|overlapping|conflicting)"
    r"-a(?P<agents>\d+)-(?P<topology>solo|peer|orchestrator)"
    r"-(?P<policy>forbidden|allowed|mandatory)-r(?P<rep>\d+)$"
)

GRAPH_METRICS = (
    "n_agent_to_agent", "n_agent_to_agent_directed",
    "n_agent_to_file", "n_file_to_agent",
)
CI_WIDTH_THRESHOLD = 0.5   # outcome precision threshold; see analysis-plan.md.
CV_THRESHOLD = 0.5         # graph-statistic precision threshold; see plan.


def parse_run_id(run_id):
    """Pull (task, pattern, agents, topology, policy, rep) out of a run id."""
    m = RUN_RE.match(run_id)
    if not m:
        return None
    return {
        "task": m["task"],
        "pattern": m["pattern"],
        "agent_count": int(m["agents"]),
        "topology": m["topology"],
        "artefact_policy": m["policy"],
        "replication": int(m["rep"]),
    }


def wilson_ci(k, n, z=1.96):
    """Wilson score interval for a binomial proportion (95% by default)."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def load_ok_run_ids(ledger_path):
    """Set of run_ids with status == "ok" in the ledger.

    Used to filter ghost rows out of `runs.csv`. A run that errored
    (rate-limit reject, launcher crash, etc.) can still leave a
    partial dataset in its per-run directory; the master combine
    then picks that dataset up as a zero-or-near-zero-count row
    indistinguishable from a real low-activity run. Cross-checking
    against the ledger drops these contributions before the cell
    statistics are computed. Combined with the runner's
    post-2026-05-28 policy of not invoking the parser on
    STATUS_ERROR, this gives belt-and-braces protection: the runner
    fix prevents new ghost rows being written; this filter rejects
    any historical ghost rows already on disk.

    Returns the empty set when the ledger does not exist or is
    unreadable, which means "no filtering applied". The caller
    treats an empty set as a signal to fall back on the raw
    `runs.csv` rows.
    """
    if not os.path.exists(ledger_path):
        return set()
    try:
        with open(ledger_path) as f:
            ledger = json.load(f)
    except (OSError, json.JSONDecodeError):
        return set()
    if isinstance(ledger, dict):
        if "runs" in ledger and isinstance(ledger["runs"], list):
            rows = ledger["runs"]
        else:
            rows = list(ledger.values())
    else:
        rows = ledger
    ok = set()
    for r in rows:
        if r.get("status") == "ok" and r.get("run_id"):
            ok.add(r["run_id"])
    return ok


def load_runs(runs_csv, ok_run_ids=None):
    """Read the master `runs.csv` and return one dict per non-ghost run.

    `ok_run_ids` is the set returned by `load_ok_run_ids`. When non-empty,
    rows whose `run_id` is absent from the set are dropped (ghost rows
    from errored runs). An empty set disables the filter.
    """
    rows = []
    dropped = 0
    with open(runs_csv, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            parts = parse_run_id(row["run_id"])
            if parts is None:
                continue
            if ok_run_ids and row["run_id"] not in ok_run_ids:
                dropped += 1
                continue
            row.update(parts)
            row["success_b"] = (row["success"].lower() == "true")
            for k in GRAPH_METRICS + ("n_file_nodes", "completion_time_s"):
                try:
                    row[k] = float(row[k])
                except (KeyError, ValueError, TypeError):
                    row[k] = float("nan")
            rows.append(row)
    return rows, dropped


def group_by_cell_pattern(rows):
    groups = defaultdict(list)
    for row in rows:
        key = (
            row["agent_count"], row["topology"], row["artefact_policy"],
            row["pattern"],
        )
        groups[key].append(row)
    return groups


def cell_label(key):
    agents, topology, policy, pattern = key
    return f"a{agents}-{topology}-{policy}/{pattern}"


def summarise_cell(rows):
    n = len(rows)
    successes = sum(1 for r in rows if r["success_b"])
    success_rate = successes / n if n > 0 else float("nan")
    ci_low, ci_high = wilson_ci(successes, n)
    ci_width = ci_high - ci_low

    stats = {
        "n": n,
        "successes": successes,
        "success_rate": success_rate,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "ci_width": ci_width,
    }

    for metric in GRAPH_METRICS + ("n_file_nodes", "completion_time_s"):
        values = [r[metric] for r in rows if not math.isnan(r[metric])]
        if len(values) >= 2:
            mean = statistics.fmean(values)
            sd = statistics.stdev(values)
        elif len(values) == 1:
            mean = values[0]
            sd = float("nan")
        else:
            mean = float("nan")
            sd = float("nan")
        if mean and not math.isnan(mean) and mean != 0 and not math.isnan(sd):
            cv = sd / mean
        else:
            cv = float("nan")
        stats[f"{metric}_mean"] = mean
        stats[f"{metric}_sd"] = sd
        stats[f"{metric}_cv"] = cv

    return stats


def flag_topup(stats):
    """Apply the pre-registered top-up rule. Return the list of reasons."""
    reasons = []
    if stats["ci_width"] > CI_WIDTH_THRESHOLD:
        reasons.append(
            f"outcome CI width = {stats['ci_width']:.2f} > {CI_WIDTH_THRESHOLD}"
        )
    for metric in GRAPH_METRICS:
        cv = stats[f"{metric}_cv"]
        mean = stats[f"{metric}_mean"]
        # CV is meaningful only when the metric is consistently non-zero. For
        # near-zero count metrics the CV is structurally large (a property of
        # the data, not a precision problem more reps would fix). See the
        # refinement note in memory/experiments/family-1-full/analysis-plan.md.
        if math.isnan(mean) or mean < 1.0:
            continue
        if not math.isnan(cv) and cv > CV_THRESHOLD:
            reasons.append(
                f"{metric} CV = {cv:.2f} > {CV_THRESHOLD}"
            )
    return reasons


def matrix_sort_key(key):
    agents, topology, policy, pattern = key
    topo_order = {"solo": 0, "orchestrator": 1, "peer": 2}
    policy_order = {"forbidden": 0, "allowed": 1, "mandatory": 2}
    pattern_order = {"clean": 0, "overlapping": 1, "conflicting": 2}
    return (agents, topo_order[topology], policy_order[policy],
            pattern_order[pattern])


def read_ledger_summary(ledger_path):
    if not os.path.exists(ledger_path):
        return None
    with open(ledger_path) as f:
        ledger = json.load(f)
    # The ledger is keyed by run_id at top level (one dict per run).
    if isinstance(ledger, dict):
        # Distinguish a {"runs": [...]} envelope from the {run_id: row} form.
        if "runs" in ledger and isinstance(ledger["runs"], list):
            rows = ledger["runs"]
        else:
            rows = list(ledger.values())
    else:
        rows = ledger
    runs = len(rows)
    ok = sum(1 for r in rows if r.get("status") == "ok")
    error = sum(1 for r in rows if r.get("status") == "error")
    succeeded = sum(1 for r in rows if r.get("success") in (True, "True", "true"))
    failed = ok - succeeded
    return {"runs": runs, "ok": ok, "error": error,
            "succeeded": succeeded, "failed": failed}


def render_report(summary, groups, out_path):
    lines = []
    lines.append("# Family 1 full schedule, preliminary report")
    lines.append("")
    lines.append("Generated by `scripts/analyse_family1_full.py` against the")
    lines.append("current contents of `runs.csv`. The decision rules applied")
    lines.append("here are the pre-registered ones in")
    lines.append("`memory/experiments/family-1-full/analysis-plan.md`.")
    lines.append("")
    lines.append("## Batch state")
    if summary:
        lines.append(f"- Runs recorded in ledger: {summary['runs']}")
        lines.append(f"- status = ok: {summary['ok']}")
        lines.append(f"- status = error: {summary['error']}")
        lines.append(f"- verifier succeeded: {summary['succeeded']}")
        lines.append(f"- verifier failed: {summary['failed']}")
        ghosts = summary.get("ghost_rows_dropped", 0)
        if ghosts:
            lines.append(f"- ghost rows dropped from runs.csv: {ghosts}")
    else:
        lines.append("- (ledger not found)")
    lines.append("")
    lines.append("## Per-cell-and-pattern summary")
    lines.append("")
    lines.append("| cell / pattern | N | succ | success rate (95% CI) | a2a / directed (sd) | a2f (sd) | f2a (sd) | files (sd) | wall (sd) | top-up? |")
    lines.append("|---|---:|---:|---|---|---|---|---|---|---|")

    topup_list = []
    for key in sorted(groups.keys(), key=matrix_sort_key):
        rows = groups[key]
        stats = summarise_cell(rows)
        flags = flag_topup(stats)

        sr = f"{stats['success_rate']:.2f} ({stats['ci_low']:.2f}-{stats['ci_high']:.2f})"
        # The a2a column reports both the total event count (the
        # invariant from before the 2026-05-30 addressing-convention
        # change) and the directed subset (canonical + alias targets,
        # introduced by that change).
        a2a = (
            f"{stats['n_agent_to_agent_mean']:.1f} / "
            f"{stats['n_agent_to_agent_directed_mean']:.1f} "
            f"({stats['n_agent_to_agent_sd']:.1f})"
        )
        a2f = f"{stats['n_agent_to_file_mean']:.1f} ({stats['n_agent_to_file_sd']:.1f})"
        f2a = f"{stats['n_file_to_agent_mean']:.1f} ({stats['n_file_to_agent_sd']:.1f})"
        files = f"{stats['n_file_nodes_mean']:.1f} ({stats['n_file_nodes_sd']:.1f})"
        wall = f"{stats['completion_time_s_mean']:.0f}s ({stats['completion_time_s_sd']:.0f})"
        topup = "**yes**" if flags else "no"
        lines.append(
            f"| {cell_label(key)} | {stats['n']} | {stats['successes']} | "
            f"{sr} | {a2a} | {a2f} | {f2a} | {files} | {wall} | {topup} |"
        )
        if flags:
            topup_list.append((cell_label(key), stats["n"], flags))

    lines.append("")
    lines.append("## Top-up list (cells flagged for N = 20)")
    lines.append("")
    if not topup_list:
        lines.append("None at this point in the batch.")
    else:
        for label, n, flags in topup_list:
            lines.append(f"- **{label}** (N = {n}): " + "; ".join(flags))
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- Cells with N < 10 are partial; the top-up decision is")
    lines.append("  applied at whatever N is currently in the data, but only")
    lines.append("  the values at the final N = 10 are part of the analysis")
    lines.append("  plan's commitment.")
    lines.append("- Wilson 95 per cent intervals are used for success-rate")
    lines.append("  precision (`wilson_ci`).")
    lines.append("- CV is `sd / mean`; metrics with cell mean below 1 are")
    lines.append("  excluded from the CV check because near-zero count")
    lines.append("  metrics have structurally large CV (see analysis-plan.md).")
    lines.append("")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Family 1 full schedule preliminary analysis.")
    parser.add_argument(
        "--experiment-root", default="data/family-1-full")
    parser.add_argument(
        "--output", default="memory/experiments/family-1-full/preliminary.md")
    args = parser.parse_args()

    runs_root = os.path.join(args.experiment_root, "runs")
    master_dir = os.path.join(args.experiment_root, "master")
    runs_csv = os.path.join(master_dir, "runs.csv")
    ledger_json = os.path.join(args.experiment_root, "ledger.json")

    # Rebuild the master CSVs from every per-run datasets/ directory so the
    # analysis runs against fresh aggregate while the batch is still going
    # (the runner only calls combine() at the end of the batch).
    if os.path.isdir(runs_root):
        per_run_datasets = sorted(
            d for d in glob.glob(os.path.join(runs_root, "*", "datasets"))
            if os.path.isdir(d)
        )
        if per_run_datasets:
            combine_datasets(per_run_datasets, master_dir)

    if not os.path.exists(runs_csv):
        print(f"runs.csv not found at {runs_csv}; nothing to analyse.")
        sys.exit(0)

    ok_run_ids = load_ok_run_ids(ledger_json)
    rows, dropped = load_runs(runs_csv, ok_run_ids=ok_run_ids)
    groups = group_by_cell_pattern(rows)
    summary = read_ledger_summary(ledger_json)
    if summary is not None:
        summary["ghost_rows_dropped"] = dropped

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    render_report(summary, groups, args.output)
    print(f"wrote {args.output}")

    if summary:
        print(f"ledger: {summary['ok']} ok, {summary['error']} error, "
              f"{summary['succeeded']} succeeded, {summary['failed']} failed")
    if dropped:
        print(f"ghost rows dropped from runs.csv (not in ledger ok set): "
              f"{dropped}")
    print(f"cell-and-pattern combinations observed: {len(groups)}")
    full_n_cells = sum(1 for v in groups.values() if len(v) >= 10)
    print(f"combinations with N >= 10: {full_n_cells}")


if __name__ == "__main__":
    main()
