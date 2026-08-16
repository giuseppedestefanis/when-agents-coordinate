#!/usr/bin/env python3
"""RQ2 (dynamics) preliminary analysis pipeline.

Computes the temporal-dynamics metrics defined in
`memory/experiments/rq2-dynamics/analysis-plan.md` from the per-edge
`edges.csv` of a collected experiment, aggregates them per configuration
cell and per family, and writes a markdown report.

Unlike the Family 1/2 outcome pipelines, this script reads `edges.csv`
(every edge carries a timestamp and type), not the aggregated `runs.csv`.
Runs are filtered to the ledger `ok` set (the same ghost-row protection),
so an in-flight or errored run never contaminates the dynamics summary.

The script is family- and experiment-agnostic:

    .venv/bin/python scripts/analyse_rq2_dynamics.py \
        --experiment-root data/family-2-full \
        --out memory/experiments/rq2-dynamics/family-2-preliminary.md

Descriptive at this stage; no inferential test is pre-registered yet (see
the analysis plan). The report regenerates from the data on every run.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_comms.parser.datasets import combine_datasets


RUN_RE = re.compile(
    r"^family-(?P<family>\d+)-(?P<task>[a-z_0-9]+)"
    r"-(?P<pattern>clean|overlapping|conflicting)"
    r"-a(?P<agents>\d+)-(?P<topology>solo|peer|orchestrator)"
    r"-(?P<policy>forbidden|allowed|mandatory)-r(?P<rep>\d+)$"
)

# Short names for the three edge types, used throughout the metrics.
TYPE_MAP = {
    "a2a": "agent_to_agent",
    "a2f": "agent_to_file",
    "f2a": "file_to_agent",
}
N_BINS = 10
MIN_EDGES_FOR_RATE = 3  # burstiness / idle-gap / gini need >= 3 edges


def parse_run_id(run_id):
    m = RUN_RE.match(run_id)
    if not m:
        return None
    return {
        "family": m["family"],
        "task": m["task"],
        "pattern": m["pattern"],
        "agent_count": int(m["agents"]),
        "topology": m["topology"],
        "artefact_policy": m["policy"],
        "rep": int(m["rep"]),
    }


def load_ok_run_ids(ledger_path):
    if not os.path.exists(ledger_path):
        return set()
    try:
        with open(ledger_path) as f:
            ledger = json.load(f)
    except (OSError, json.JSONDecodeError):
        return set()
    if isinstance(ledger, dict):
        rows = ledger["runs"] if isinstance(ledger.get("runs"), list) \
            else list(ledger.values())
    else:
        rows = ledger
    return {r["run_id"] for r in rows
            if r.get("status") == "ok" and r.get("run_id")}


def parse_ts(s):
    """Parse the two ISO-8601 shapes the parser emits (Z and +00:00)."""
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def load_edges_by_run(edges_csv, ok_run_ids=None):
    """Return {run_id: [edge dicts]} for all edge types, ok runs only."""
    by_run = defaultdict(list)
    if not os.path.exists(edges_csv):
        return by_run
    with open(edges_csv, newline="") as f:
        for row in csv.DictReader(f):
            rid = row.get("run_id")
            if ok_run_ids and rid not in ok_run_ids:
                continue
            if not row.get("timestamp"):
                continue
            by_run[rid].append(row)
    return by_run


def _gini(xs):
    xs = sorted(xs)
    n = len(xs)
    s = sum(xs)
    if n == 0 or s == 0:
        return 0.0
    cum = sum((i + 1) * x for i, x in enumerate(xs))
    return (2.0 * cum) / (n * s) - (n + 1.0) / n


def run_metrics(edges):
    """Per-run temporal metrics for one run's edge list."""
    parsed = sorted(
        ((parse_ts(e["timestamp"]), e["edge_type"], e["source"], e["target"])
         for e in edges),
        key=lambda x: x[0],
    )
    m = len(parsed)
    out = {"n_edges": m}
    for short, full in TYPE_MAP.items():
        out[f"n_{short}"] = sum(1 for p in parsed if p[1] == full)

    if m < 2:
        out["duration_s"] = 0.0
        return out

    t0, tN = parsed[0][0], parsed[-1][0]
    dur = (tN - t0).total_seconds()
    out["duration_s"] = dur
    taus = [((p[0] - t0).total_seconds() / dur) if dur > 0 else 0.0
            for p in parsed]

    # Phase ordering: temporal centre of mass per edge type.
    for short, full in TYPE_MAP.items():
        xs = [tau for tau, p in zip(taus, parsed) if p[1] == full]
        out[f"com_{short}"] = statistics.mean(xs) if xs else math.nan
    if not math.isnan(out["com_a2a"]) and not math.isnan(out["com_a2f"]):
        out["phase_gap"] = out["com_a2f"] - out["com_a2a"]
    else:
        out["phase_gap"] = math.nan

    # Activity profile: edge counts per decile, overall and per type.
    def _bin(tau):
        return min(int(tau * N_BINS), N_BINS - 1)
    profile = {short: [0] * N_BINS for short in TYPE_MAP}
    profile["all"] = [0] * N_BINS
    inv = {v: k for k, v in TYPE_MAP.items()}
    for tau, p in zip(taus, parsed):
        b = _bin(tau)
        profile["all"][b] += 1
        profile[inv[p[1]]][b] += 1
    out["profile"] = profile

    # Burstiness / idle gap / gap concentration.
    if m >= MIN_EDGES_FOR_RATE and dur > 0:
        gaps = [(parsed[k + 1][0] - parsed[k][0]).total_seconds()
                for k in range(m - 1)]
        mu = statistics.mean(gaps)
        sigma = statistics.pstdev(gaps)
        out["burstiness"] = (sigma - mu) / (sigma + mu) if (sigma + mu) else 0.0
        out["max_idle_gap_norm"] = max(gaps) / dur
        out["gap_gini"] = _gini(gaps)
    else:
        out["burstiness"] = math.nan
        out["max_idle_gap_norm"] = math.nan
        out["gap_gini"] = math.nan

    # Edge persistence.
    fired = Counter((p[2], p[3], p[1]) for p in parsed)
    firstlast = defaultdict(lambda: [1.0, 0.0])
    for tau, p in zip(taus, parsed):
        fl = firstlast[(p[2], p[3], p[1])]
        fl[0] = min(fl[0], tau)
        fl[1] = max(fl[1], tau)
    n_distinct = len(fired)
    out["n_distinct_edges"] = n_distinct
    out["frac_oneshot"] = sum(1 for c in fired.values() if c == 1) / n_distinct
    out["max_recurrence"] = max(fired.values())
    recurring = [firstlast[k] for k, c in fired.items() if c >= 2]
    out["recurring_lifespan"] = (
        statistics.mean(fl[1] - fl[0] for fl in recurring)
        if recurring else math.nan
    )
    return out


SCALARS = (
    "n_edges", "duration_s", "burstiness", "max_idle_gap_norm", "gap_gini",
    "com_a2a", "com_a2f", "phase_gap", "frac_oneshot", "max_recurrence",
    "recurring_lifespan", "n_distinct_edges",
)


def _agg(values):
    vals = [v for v in values if v is not None and not (
        isinstance(v, float) and math.isnan(v))]
    if not vals:
        return (math.nan, math.nan, 0)
    mean = statistics.mean(vals)
    sd = statistics.stdev(vals) if len(vals) > 1 else 0.0
    return (mean, sd, len(vals))


def aggregate(per_run):
    """Group per-run metric dicts into per-cell aggregates."""
    cells = defaultdict(list)
    for parts, m in per_run:
        key = (parts["agent_count"], parts["topology"],
               parts["artefact_policy"], parts["pattern"], parts["task"])
        cells[key].append(m)
    summary = {}
    for key, ms in cells.items():
        agg = {s: _agg([m.get(s) for m in ms]) for s in SCALARS}
        ordered = [m for m in ms
                   if not math.isnan(m.get("com_a2a", math.nan))
                   and not math.isnan(m.get("com_a2f", math.nan))]
        agg["phase_order_share"] = (
            sum(1 for m in ordered if m["com_a2a"] < m["com_a2f"]) / len(ordered)
            if ordered else math.nan
        )
        agg["n_runs"] = len(ms)
        summary[key] = agg
    return summary


def mean_profile(per_run):
    """Population mean decile profile per edge type (fraction of edges)."""
    totals = {short: [0.0] * N_BINS for short in list(TYPE_MAP) + ["all"]}
    counts = {short: 0 for short in totals}
    for _parts, m in per_run:
        prof = m.get("profile")
        if not prof:
            continue
        for short, vec in prof.items():
            tot = sum(vec)
            if tot == 0:
                continue
            for i, v in enumerate(vec):
                totals[short][i] += v / tot
            counts[short] += 1
    out = {}
    for short, vec in totals.items():
        n = counts[short]
        out[short] = [v / n for v in vec] if n else [math.nan] * N_BINS
    return out


def _fmt(triple):
    mean, sd, n = triple
    if math.isnan(mean):
        return "  n/a  "
    return f"{mean:.2f} ({sd:.2f})"


def write_report(out_path, root, per_run, summary, profile, n_excluded):
    lines = []
    lines.append("# RQ2 dynamics: preliminary report")
    lines.append("")
    lines.append(f"Source: `{root}` | runs analysed: {len(per_run)} "
                 f"| runs with < {MIN_EDGES_FOR_RATE} edges "
                 f"(rate metrics excluded): {n_excluded}")
    lines.append("")
    lines.append("Regenerated by `scripts/analyse_rq2_dynamics.py`. "
                 "Definitions in "
                 "`memory/experiments/rq2-dynamics/analysis-plan.md`. "
                 "Descriptive only.")
    lines.append("")

    lines.append("## Population activity profile (mean fraction of edges per decile)")
    lines.append("")
    header = "| type | " + " | ".join(f"d{i+1}" for i in range(N_BINS)) + " |"
    lines.append(header)
    lines.append("|" + "---|" * (N_BINS + 1))
    for short in ("all", "a2a", "a2f", "f2a"):
        vec = profile.get(short, [math.nan] * N_BINS)
        cells = " | ".join(f"{v:.2f}" if not math.isnan(v) else "n/a"
                           for v in vec)
        lines.append(f"| {short} | {cells} |")
    lines.append("")

    lines.append("## Per-cell temporal metrics")
    lines.append("")
    lines.append("Columns: mean (sd) over the cell's runs. "
                 "`burst` = burstiness B in [-1,1]; `idle` = largest "
                 "normalised idle gap; `gini` = gap Gini; "
                 "`com_a2a`/`com_a2f` = temporal centre of mass; "
                 "`phase>` = share of runs with com_a2a < com_a2f; "
                 "`1shot` = fraction one-shot edges; "
                 "`rec_life` = recurring-edge lifespan.")
    lines.append("")
    cols = ("| cell | n | burst | idle | gini | com_a2a | com_a2f "
            "| phase> | 1shot | rec_life |")
    lines.append(cols)
    lines.append("|" + "---|" * 10)
    for key in sorted(summary):
        a, topo, pol, pat, task = key
        s = summary[key]
        pshare = s["phase_order_share"]
        pshare_s = "n/a" if math.isnan(pshare) else f"{pshare:.2f}"
        label = f"a{a}-{topo}-{pol}-{pat}"
        if task not in ("process_orders", "summarise_transactions"):
            label += f"/{task}"
        lines.append(
            f"| {label} | {s['n_runs']} | {_fmt(s['burstiness'])} "
            f"| {_fmt(s['max_idle_gap_norm'])} | {_fmt(s['gap_gini'])} "
            f"| {_fmt(s['com_a2a'])} | {_fmt(s['com_a2f'])} "
            f"| {pshare_s} | {_fmt(s['frac_oneshot'])} "
            f"| {_fmt(s['recurring_lifespan'])} |"
        )
    lines.append("")

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        f.write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser(description="RQ2 dynamics analysis.")
    ap.add_argument("--experiment-root", default="data/family-2-full")
    ap.add_argument("--out",
                    default="memory/experiments/rq2-dynamics/"
                            "family-2-preliminary.md")
    ap.add_argument("--combine", action="store_true",
                    help="rebuild master CSVs from per-run datasets first")
    args = ap.parse_args()

    root = args.experiment_root
    master = os.path.join(root, "master")
    if args.combine:
        per_run = os.path.join(root, "runs")
        combine_datasets(per_run, master)

    ledger_json = os.path.join(root, "ledger.json")
    ok = load_ok_run_ids(ledger_json)
    edges_csv = os.path.join(master, "edges.csv")
    by_run = load_edges_by_run(edges_csv, ok_run_ids=ok or None)

    per_run = []
    n_excluded = 0
    for rid, edges in by_run.items():
        parts = parse_run_id(rid)
        if parts is None:
            continue
        m = run_metrics(edges)
        if m["n_edges"] < MIN_EDGES_FOR_RATE:
            n_excluded += 1
        per_run.append((parts, m))

    summary = aggregate(per_run)
    profile = mean_profile(per_run)
    write_report(args.out, root, per_run, summary, profile, n_excluded)
    print(f"RQ2 dynamics: {len(per_run)} runs, {len(summary)} cells "
          f"-> {args.out}")


if __name__ == "__main__":
    main()
