#!/usr/bin/env python3
"""Family 2 full schedule, preliminary analysis pipeline.

Applies the pre-registered analysis plan at
`memory/experiments/family-2-full/analysis-plan.md`. Mirrors
`scripts/analyse_family1_full.py` on the cell-level summary and the
top-up rule, and adds the per-hypothesis test runner for H1-H7.

The pipeline reads the master CSVs at
`data/family-2-full/master/{runs,edges}.csv`, optionally rebuilds
them from the per-run datasets, and writes
`memory/experiments/family-2-full/preliminary.md`. The per-hypothesis
results only land in the report when all hypothesis-relevant cells
have reached the pre-registered N (N=10 by default).

Usage:

    .venv/bin/python scripts/analyse_family2_full.py

Threshold inheritance: 0.5 CI width on outcome precision, 0.5 CV on
graph-statistic precision (cells with mean < 1 are excluded from the
CV check). Identical to Family 1's plan and locked at the
pre-registration date 2026-05-30.
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
    r"^family-2-(?P<task>[a-z_0-9]+)-(?P<pattern>clean|overlapping|conflicting)"
    r"-a(?P<agents>\d+)-(?P<topology>solo|peer|orchestrator)"
    r"-(?P<policy>forbidden|allowed|mandatory)-r(?P<rep>\d+)$"
)

GRAPH_METRICS = (
    "n_agent_to_agent", "n_agent_to_agent_directed",
    "n_agent_to_file", "n_file_to_agent",
)
TARGET_KINDS = ("canonical", "alias", "broadcast", "role", "unknown")
CI_WIDTH_THRESHOLD = 0.5
CV_THRESHOLD = 0.5
PRE_REGISTERED_N = 10

# Fixed Family 1 baseline values for H5. Read from the Family 1
# regeneration diff dated 2026-05-30.
#
# NOTE (2026-06-10 provenance): 0.968 is the pre-registration commitment
# value and is the POOLED-EDGE directed share at the F1 cell
# (4, peer, allowed, clean): 27.6 / 28.5 of all 285 a2a edges. The current
# released master (commit f8994b3) yields a MEAN-OF-PER-RUN directed share
# of 0.9709 at the same cell (seven runs at 1.0 plus 0.900, 0.906, 0.903).
# The 96.8% vs 97.1% difference is an estimator choice (pooled-edge ratio
# vs mean-of-per-run ratio) on the SAME master, not a stale regeneration.
# Kept frozen as the labelled pre-registration baseline.
F1_DIRECTED_SHARE_BASELINE_CELL = 0.968   # peer/allowed/clean, n=4

# H7 conflict footprint: the two boundary tests an Instance-5 (B2)
# conflict-converged failure is designed to fail, with the other 23 passing.
H7_FOOTPRINT_TESTS = frozenset({
    "test_validate_zero_amount_kept",
    "test_end_to_end_zero_amount_record_included",
})


def benjamini_hochberg(pmap):
    """Benjamini-Hochberg step-up adjusted p-values.

    pmap maps a comparison id to its raw p-value. Returns a dict mapping
    each id to its BH-adjusted p-value (monotone, capped at 1.0).
    """
    items = sorted(pmap.items(), key=lambda kv: kv[1])
    m = len(items)
    adj = {}
    prev = 1.0
    for rank in range(m, 0, -1):       # largest p (rank m) down to smallest
        key, p = items[rank - 1]
        val = min(prev, p * m / rank)
        adj[key] = min(val, 1.0)
        prev = adj[key]
    return adj


def _failing_tests_for_run(run_dir, python=None, timeout=120):
    """Re-run a finished run's verifier and return the set of failing test
    names (failures and errors). Returns None if the run cannot be verified.

    The verifier is re-executed exactly as the runner did (fresh subprocess,
    the run's workspace on PYTHONPATH), so per-test identities are recovered
    deterministically from the static deliverables on disk.
    """
    import subprocess
    verifier = os.path.abspath(os.path.join(run_dir, "verifier", "verifier.py"))
    workspace = os.path.abspath(os.path.join(run_dir, "workspace"))
    verifier_dir = os.path.dirname(verifier)
    if not os.path.exists(verifier) or not os.path.isdir(workspace):
        return None
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        p for p in (workspace, env.get("PYTHONPATH", "")) if p)
    cmd = [python or sys.executable, "-m", "pytest", verifier,
           "-q", "--no-header", "-p", "no:cacheprovider", "-rfE", "--tb=no"]
    try:
        proc = subprocess.run(
            cmd, cwd=verifier_dir, env=env,
            capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None
    failed = set()
    for line in (proc.stdout + proc.stderr).splitlines():
        m = re.match(r"^(?:FAILED|ERROR)\s+\S+::([A-Za-z0-9_]+)", line)
        if m:
            failed.add(m.group(1))
    return failed


def run_h7_census(experiment_root, identity=False, python=None):
    """Census of conflicting-cell verifier failures for H7.

    Always reads result.json for the (passed, failed, errors) count footprint.
    When identity=True, additionally re-runs each failing run's verifier to
    confirm the failing-test set is exactly H7_FOOTPRINT_TESTS (this is the
    expensive part: one pytest subprocess per failing run).
    """
    import glob as _glob
    summary = {"total": 0, "failing": 0, "footprint_23_2_0": 0,
               "identity_ran": False, "identity_total": 0,
               "identity_match": 0, "mismatches": []}
    pattern = os.path.join(experiment_root, "runs", "*conflicting*",
                           "result.json")
    for rj in sorted(_glob.glob(pattern)):
        try:
            with open(rj) as f:
                d = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        summary["total"] += 1
        if d.get("success"):
            continue
        summary["failing"] += 1
        if (d.get("tests_passed") == 23 and d.get("tests_failed") == 2
                and d.get("tests_errors") == 0):
            summary["footprint_23_2_0"] += 1
        if identity:
            run_dir = os.path.dirname(rj)
            failed = _failing_tests_for_run(run_dir, python=python)
            summary["identity_ran"] = True
            summary["identity_total"] += 1
            if failed is not None and failed == set(H7_FOOTPRINT_TESTS):
                summary["identity_match"] += 1
            else:
                summary["mismatches"].append(
                    (os.path.basename(run_dir),
                     sorted(failed) if failed else None))
    return summary


def parse_run_id(run_id):
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
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def load_ok_run_ids(ledger_path):
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
    rows = []
    dropped = 0
    with open(runs_csv, newline="") as f:
        for row in csv.DictReader(f):
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


def load_edges(edges_csv, ok_run_ids=None):
    """Load the master edges.csv, returning the a2a rows only."""
    rows = []
    if not os.path.exists(edges_csv):
        return rows
    with open(edges_csv, newline="") as f:
        for row in csv.DictReader(f):
            if row.get("edge_type") != "agent_to_agent":
                continue
            if ok_run_ids and row.get("run_id") not in ok_run_ids:
                continue
            rows.append(row)
    return rows


def group_by_cell_pattern_task(rows):
    groups = defaultdict(list)
    for row in rows:
        key = (
            row["agent_count"], row["topology"], row["artefact_policy"],
            row["pattern"], row["task"],
        )
        groups[key].append(row)
    return groups


def cell_label(key):
    agents, topology, policy, pattern, task = key
    return f"a{agents}-{topology}-{policy}/{pattern}/{task}"


def summarise_cell(rows, edges_by_runid=None):
    n = len(rows)
    successes = sum(1 for r in rows if r["success_b"])
    success_rate = successes / n if n > 0 else float("nan")
    ci_low, ci_high = wilson_ci(successes, n)
    ci_width = ci_high - ci_low

    stats = {
        "n": n, "successes": successes, "success_rate": success_rate,
        "ci_low": ci_low, "ci_high": ci_high, "ci_width": ci_width,
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
            mean = sd = float("nan")
        cv = (sd / mean
              if mean and not math.isnan(mean) and mean != 0
              and not math.isnan(sd) else float("nan"))
        stats[f"{metric}_mean"] = mean
        stats[f"{metric}_sd"] = sd
        stats[f"{metric}_cv"] = cv

    # target-kind shares, pooled across the cell's runs.
    if edges_by_runid is not None:
        kind_counts = {k: 0 for k in TARGET_KINDS}
        total_edges = 0
        for r in rows:
            for e in edges_by_runid.get(r["run_id"], []):
                k = e.get("target_kind", "")
                if k in kind_counts:
                    kind_counts[k] += 1
                    total_edges += 1
        for k in TARGET_KINDS:
            stats[f"share_{k}"] = (
                kind_counts[k] / total_edges if total_edges else 0.0)
        stats["pooled_a2a_edges"] = total_edges
    return stats


def flag_topup(stats):
    reasons = []
    if stats["ci_width"] > CI_WIDTH_THRESHOLD:
        reasons.append(
            f"outcome CI width = {stats['ci_width']:.2f} > "
            f"{CI_WIDTH_THRESHOLD}")
    for metric in ("n_agent_to_agent", "n_agent_to_agent_directed",
                   "n_agent_to_file", "n_file_to_agent"):
        cv = stats[f"{metric}_cv"]
        mean = stats[f"{metric}_mean"]
        if math.isnan(mean) or mean < 1.0:
            continue
        if not math.isnan(cv) and cv > CV_THRESHOLD:
            reasons.append(f"{metric} CV = {cv:.2f} > {CV_THRESHOLD}")
    return reasons


def matrix_sort_key(key):
    agents, topology, policy, pattern, task = key
    topo_order = {"solo": 0, "orchestrator": 1, "peer": 2}
    policy_order = {"forbidden": 0, "allowed": 1, "mandatory": 2}
    pattern_order = {"clean": 0, "overlapping": 1, "conflicting": 2}
    task_order = {"summarise_transactions": 0, "compute_invoices": 1,
                  "summarise_transactions_v2": 2}
    return (agents, topo_order[topology], policy_order[policy],
            pattern_order[pattern], task_order.get(task, 99))


def read_ledger_summary(ledger_path):
    if not os.path.exists(ledger_path):
        return None
    with open(ledger_path) as f:
        ledger = json.load(f)
    if isinstance(ledger, dict):
        if "runs" in ledger and isinstance(ledger["runs"], list):
            rows = ledger["runs"]
        else:
            rows = list(ledger.values())
    else:
        rows = ledger
    runs = len(rows)
    ok = sum(1 for r in rows if r.get("status") == "ok")
    error = sum(1 for r in rows if r.get("status") == "error")
    succeeded = sum(1 for r in rows
                    if r.get("success") in (True, "True", "true"))
    failed = ok - succeeded
    return {"runs": runs, "ok": ok, "error": error,
            "succeeded": succeeded, "failed": failed}


def _hypothesis_results(rows, edges_by_runid, experiment_root=None,
                        h7_identity_census=False):
    """Compute H1-H7 results when relevant cells have reached N>=10.

    Returns a list of (hypothesis_label, status, details). status is one of
    `confirmed`, `refuted`, `inconclusive`, `pending` (insufficient data),
    or `manual`.

    Directional/between-group inferential p-values (H2, H3, H4, H6) are
    pooled into one Benjamini-Hochberg family and reported both raw and
    BH-adjusted, per the pre-registered plan's multiple-comparisons rule.
    H7 is descriptive: a census of the conflicting-cell verifier-failure
    footprint, optionally confirming the exact two-test identity by
    re-running each failing verifier (h7_identity_census=True).
    """
    try:
        from scipy import stats as ss
    except ImportError:
        return [("(scipy not available; hypothesis tests skipped)",
                 "pending", "")]

    import math as _m
    groups = group_by_cell_pattern_task(rows)

    def cell(n, topology, policy, pattern, task):
        return groups.get((n, topology, policy, pattern, task), [])

    labels = {
        "H1": "H1 n² scaling on chained tasks",
        "H2": "H2 topology shapes a2a distribution",
        "H3": "H3 topology x conflict interaction",
        "H4": "H4 artefact policy reproduces F1 pattern",
        "H4-fa-scale": "H4 file-count forbidden vs allowed by team size",
        "H5": "H5 cross-family directed-share gap >= 10pp",
        "H6": "H6 v2 canonical share below summarise_transactions",
        "H7": "H7 conflict footprint reproduces",
    }
    rowmap = {}        # id -> (status, details)
    family_p = {}      # id -> raw p (pre-registered directional BH family)

    # H1: log-log slope of a2a on n at peer/allowed/clean, summarise_transactions.
    cells_h1 = [(n, cell(n, "peer", "allowed", "clean",
                          "summarise_transactions"))
                for n in (2, 4, 8)]
    if all(len(c) >= PRE_REGISTERED_N for _, c in cells_h1):
        xs, ys = [], []
        for n, rs in cells_h1:
            mean_a2a = statistics.fmean(r["n_agent_to_agent"] for r in rs)
            if mean_a2a > 0:
                xs.append(_m.log(n))
                ys.append(_m.log(mean_a2a))
        if len(xs) >= 2:
            slope, intercept, r_value, p_value, std_err = ss.linregress(xs, ys)
            ci_low = slope - 1.96 * std_err
            ci_high = slope + 1.96 * std_err
            confirmed = 1.5 <= slope <= 2.5
            rowmap["H1"] = (
                "confirmed" if confirmed else "refuted",
                f"slope = {slope:.2f}, 95% CI [{ci_low:.2f}, {ci_high:.2f}]")
        else:
            rowmap["H1"] = ("inconclusive", "insufficient non-zero cells")
    else:
        rowmap["H1"] = ("pending",
                        "needs N >= 10 at n in {2,4,8}, peer/allowed/clean")

    # H2: topology shapes a2a distribution. n=4/allowed/clean ST, peer vs
    # orchestrator on n_agent_to_agent_directed. Mann-Whitney U, two-sided
    # (null test), BH-corrected against the directional family below.
    h2_peer = cell(4, "peer", "allowed", "clean", "summarise_transactions")
    h2_orch = cell(4, "orchestrator", "allowed", "clean",
                   "summarise_transactions")
    h2_ready = (len(h2_peer) >= PRE_REGISTERED_N
                and len(h2_orch) >= PRE_REGISTERED_N)
    if h2_ready:
        peer_v = [r["n_agent_to_agent_directed"] for r in h2_peer
                  if not math.isnan(r["n_agent_to_agent_directed"])]
        orch_v = [r["n_agent_to_agent_directed"] for r in h2_orch
                  if not math.isnan(r["n_agent_to_agent_directed"])]
        u2, p2 = ss.mannwhitneyu(peer_v, orch_v, alternative="two-sided")
        family_p["H2"] = p2
        h2_peer_mean = statistics.fmean(peer_v)
        h2_orch_mean = statistics.fmean(orch_v)
    else:
        rowmap["H2"] = ("pending",
                        "needs N >= 10 at n=4 peer and orchestrator clean")

    # H3: topology x conflict interaction. n=4/allowed/conflicting ST,
    # Fisher's exact one-sided (peer succeeds at conflict more often than
    # orchestrator); bi-directional pre-registration, reported one-sided per
    # plan with the observed direction. BH-corrected in the family below.
    h3_peer = cell(4, "peer", "allowed", "conflicting",
                   "summarise_transactions")
    h3_orch = cell(4, "orchestrator", "allowed", "conflicting",
                   "summarise_transactions")
    h3_ready = (len(h3_peer) >= PRE_REGISTERED_N
                and len(h3_orch) >= PRE_REGISTERED_N)
    if h3_ready:
        pk = sum(1 for r in h3_peer if r["success_b"])
        ok = sum(1 for r in h3_orch if r["success_b"])
        pn, on = len(h3_peer), len(h3_orch)
        _, p3 = ss.fisher_exact([[pk, pn - pk], [ok, on - ok]],
                                alternative="greater")
        family_p["H3"] = p3
        h3_desc = f"peer {pk}/{pn} vs orchestrator {ok}/{on} success"
    else:
        rowmap["H3"] = ("pending",
                        "needs N >= 10 at n=4 peer and orchestrator "
                        "conflicting")

    # H4: artefact-policy on n_file_nodes at n=2, pooling topologies / patterns.
    n2_by_policy = defaultdict(list)
    for r in rows:
        if (r["agent_count"] == 2 and r["task"] == "summarise_transactions"
                and not math.isnan(r["n_file_nodes"])):
            n2_by_policy[r["artefact_policy"]].append(r["n_file_nodes"])
    h4_ready = all(len(n2_by_policy.get(p, [])) >= 9 * PRE_REGISTERED_N
                   for p in ("forbidden", "allowed", "mandatory"))
    if h4_ready:
        f, a, m = (n2_by_policy["forbidden"], n2_by_policy["allowed"],
                   n2_by_policy["mandatory"])
        u_fa, p_fa = ss.mannwhitneyu(f, a, alternative="two-sided")
        u_fm, p_fm = ss.mannwhitneyu(f, m, alternative="two-sided")
        u_am, p_am = ss.mannwhitneyu(a, m, alternative="two-sided")
        family_p["H4:f-a"] = p_fa
        family_p["H4:f-m"] = p_fm
        family_p["H4:a-m"] = p_am
    else:
        rowmap["H4"] = ("pending", "needs N >= 90 per policy at n=2")

    # H4 descriptive extension (§5.4): forbidden-vs-allowed file-count contrast
    # by team size. The pre-registered H4 above is the n=2 pooled test; the
    # n=4 and n=8 contrasts show the policy separation emerges at larger teams.
    # n_file_nodes, summarise_transactions, pooled over topologies and
    # patterns (N=90 per policy). Two-sided Mann-Whitney, reported RAW — these
    # are descriptive and not part of the pre-registered BH family.
    fa_by_n = {}
    for n in (2, 4, 8):
        by_pol = defaultdict(list)
        for r in rows:
            if (r["agent_count"] == n and r["task"] == "summarise_transactions"
                    and not math.isnan(r["n_file_nodes"])):
                by_pol[r["artefact_policy"]].append(r["n_file_nodes"])
        f_, a_ = by_pol.get("forbidden", []), by_pol.get("allowed", [])
        if len(f_) >= PRE_REGISTERED_N and len(a_) >= PRE_REGISTERED_N:
            u_, p_ = ss.mannwhitneyu(f_, a_, alternative="two-sided")
            fa_by_n[n] = (statistics.fmean(f_), statistics.fmean(a_),
                          p_, len(f_), len(a_))
    if fa_by_n:
        rowmap["H4-fa-scale"] = (
            "descriptive",
            "; ".join(
                f"n={n}: forb {fm:.2f} vs allow {am:.2f} "
                f"(N={nf}/{na}), p={p_:.3g}"
                for n, (fm, am, p_, nf, na) in sorted(fa_by_n.items())))

    # H5: F2 directed share at baseline cell vs fixed F1 96.8%. CI-based
    # decision (no p-value; not part of the BH family).
    baseline = cell(4, "peer", "allowed", "clean", "summarise_transactions")
    if len(baseline) >= PRE_REGISTERED_N:
        per_run_share = []
        for r in baseline:
            total = r["n_agent_to_agent"]
            directed = r["n_agent_to_agent_directed"]
            if total > 0:
                per_run_share.append(directed / total)
        if per_run_share:
            mean_share = statistics.fmean(per_run_share)
            sd_share = (statistics.stdev(per_run_share)
                        if len(per_run_share) >= 2 else 0.0)
            n = len(per_run_share)
            ci_high = mean_share + 1.96 * sd_share / math.sqrt(n)
            confirmed = ci_high < (F1_DIRECTED_SHARE_BASELINE_CELL - 0.10)
            rowmap["H5"] = (
                "confirmed" if confirmed else "refuted",
                (f"F2 mean = {mean_share:.3f}, upper 95% CI = {ci_high:.3f}; "
                 f"F1 baseline = {F1_DIRECTED_SHARE_BASELINE_CELL:.3f}"))
    else:
        rowmap["H5"] = ("pending", "needs N >= 10 at baseline cell")

    # H6: v2 canonical share vs summarise_transactions canonical share.
    st_cell = baseline
    v2_cell = cell(4, "peer", "allowed", "clean", "summarise_transactions_v2")
    h6_ready = (len(st_cell) >= PRE_REGISTERED_N
                and len(v2_cell) >= PRE_REGISTERED_N)
    h6_ok = False
    if h6_ready:
        st_can = sum(1 for r in st_cell
                     for e in edges_by_runid.get(r["run_id"], [])
                     if e.get("target_kind") == "canonical")
        st_total = sum(len(edges_by_runid.get(r["run_id"], [])) for r in st_cell)
        v2_can = sum(1 for r in v2_cell
                     for e in edges_by_runid.get(r["run_id"], [])
                     if e.get("target_kind") == "canonical")
        v2_total = sum(len(edges_by_runid.get(r["run_id"], [])) for r in v2_cell)
        if st_total > 0 and v2_total > 0:
            st_share = st_can / st_total
            v2_share = v2_can / v2_total
            table = [[v2_can, v2_total - v2_can],
                     [st_can, st_total - st_can]]
            _, p6 = ss.fisher_exact(table, alternative="less")
            family_p["H6"] = p6
            h6_gap = st_share - v2_share
            h6_ok = True
    if not h6_ready:
        rowmap["H6"] = ("pending", "needs N >= 10 at both cells")

    # --- Benjamini-Hochberg across the pre-registered directional family ---
    adj = benjamini_hochberg(family_p) if family_p else {}

    if h2_ready:
        confirmed = family_p["H2"] >= 0.05   # null test: no rejection expected
        rowmap["H2"] = (
            "null not rejected" if confirmed else "difference detected",
            (f"peer mean={h2_peer_mean:.1f}, orch mean={h2_orch_mean:.1f}, "
             f"U={u2:.1f}, p={family_p['H2']:.4f}, "
             f"p_BH={adj['H2']:.4f}"))
    if h3_ready:
        confirmed = adj["H3"] < 0.05
        rowmap["H3"] = (
            "interaction (BH sig.)" if confirmed else "no interaction (n.s.)",
            (f"{h3_desc}; Fisher one-sided p={family_p['H3']:.4f}, "
             f"p_BH={adj['H3']:.4f}"))
    if h4_ready:
        confirmed = (p_fa > 0.05 and p_fm < 0.05 and p_am < 0.05)
        rowmap["H4"] = (
            "confirmed" if confirmed else "refuted",
            (f"f-a p={p_fa:.3g} (BH {adj['H4:f-a']:.3g}); "
             f"f-m p={p_fm:.3g} (BH {adj['H4:f-m']:.3g}); "
             f"a-m p={p_am:.3g} (BH {adj['H4:a-m']:.3g})"))
    if h6_ok:
        confirmed = adj["H6"] < 0.05 and h6_gap >= 0.15
        rowmap["H6"] = (
            "confirmed" if confirmed else "refuted",
            (f"st canonical={st_share:.3f}, v2={v2_share:.3f}, "
             f"gap={h6_gap:.3f}, p={family_p['H6']:.3g}, "
             f"p_BH={adj['H6']:.3g}"))

    # H7: descriptive census of the conflicting-cell verifier-failure footprint.
    if experiment_root:
        cen = run_h7_census(experiment_root, identity=h7_identity_census)
        if cen["failing"]:
            frac = cen["footprint_23_2_0"] / cen["failing"]
            status = "confirmed" if frac >= 0.90 else "refuted"
            detail = (f"{cen['failing']}/{cen['total']} conflicting runs "
                      f"failed; 23/2/0 count footprint in "
                      f"{cen['footprint_23_2_0']}/{cen['failing']} "
                      f"({frac*100:.1f}%)")
            if cen["identity_ran"]:
                detail += (f"; exact two-test identity "
                           f"{cen['identity_match']}/{cen['identity_total']}")
                if cen["mismatches"]:
                    detail += f" ({len(cen['mismatches'])} mismatch)"
                else:
                    detail += " (all match)"
            else:
                detail += "; identities not re-verified (use --h7-census)"
            rowmap["H7"] = (status, detail)
        else:
            rowmap["H7"] = ("inconclusive", "no conflicting-cell failures found")
    else:
        rowmap["H7"] = ("manual", "experiment_root not provided")

    return [(labels[k],) + rowmap[k] for k in
            ("H1", "H2", "H3", "H4", "H4-fa-scale", "H5", "H6", "H7")
            if k in rowmap]


def render_report(summary, groups, edges_by_runid, hypothesis_results, out_path):
    lines = []
    lines.append("# Family 2 full schedule, preliminary report")
    lines.append("")
    lines.append("Generated by `scripts/analyse_family2_full.py` against the")
    lines.append("current contents of `runs.csv` and `edges.csv`. The decision")
    lines.append("rules applied here are the pre-registered ones in")
    lines.append("`memory/experiments/family-2-full/analysis-plan.md`.")
    lines.append("")
    lines.append("## Batch state")
    if summary:
        lines.append(f"- Runs recorded in ledger: {summary['runs']}")
        lines.append(f"- status = ok: {summary['ok']}")
        lines.append(f"- status = error: {summary['error']}")
        lines.append(f"- verifier succeeded: {summary['succeeded']}")
        lines.append(f"- verifier failed: {summary['failed']}")
        if summary.get("ghost_rows_dropped"):
            lines.append(f"- ghost rows dropped from runs.csv: "
                         f"{summary['ghost_rows_dropped']}")
    else:
        lines.append("- (ledger not found)")
    lines.append("")
    lines.append("## Per-cell summary")
    lines.append("")
    lines.append("Columns: cell/pattern/task, N, successes, success rate "
                 "(95% Wilson CI), a2a total / directed (sd), a2f mean (sd), "
                 "f2a mean (sd), files mean (sd), target_kind shares "
                 "(canonical / alias / broadcast / role / unknown), wall (sd), "
                 "top-up flag.")
    lines.append("")
    lines.append(
        "| cell / pattern / task | N | succ | success | a2a tot / dir (sd) | "
        "a2f (sd) | f2a (sd) | files (sd) | "
        "can / al / bc / ro / un | wall (sd) | top-up? |")
    lines.append("|---|---:|---:|---|---|---|---|---|---|---|---|")

    topup_list = []
    for key in sorted(groups.keys(), key=matrix_sort_key):
        rows = groups[key]
        stats = summarise_cell(rows, edges_by_runid)
        flags = flag_topup(stats)
        sr = (f"{stats['success_rate']:.2f} "
              f"({stats['ci_low']:.2f}-{stats['ci_high']:.2f})")
        a2a = (f"{stats['n_agent_to_agent_mean']:.1f} / "
               f"{stats['n_agent_to_agent_directed_mean']:.1f} "
               f"({stats['n_agent_to_agent_sd']:.1f})")
        a2f = (f"{stats['n_agent_to_file_mean']:.1f} "
               f"({stats['n_agent_to_file_sd']:.1f})")
        f2a = (f"{stats['n_file_to_agent_mean']:.1f} "
               f"({stats['n_file_to_agent_sd']:.1f})")
        files = (f"{stats['n_file_nodes_mean']:.1f} "
                 f"({stats['n_file_nodes_sd']:.1f})")
        shares = " / ".join(
            f"{stats.get(f'share_{k}', 0.0)*100:.0f}%" for k in TARGET_KINDS)
        wall = (f"{stats['completion_time_s_mean']:.0f}s "
                f"({stats['completion_time_s_sd']:.0f})")
        topup = "**yes**" if flags else "no"
        lines.append(
            f"| {cell_label(key)} | {stats['n']} | {stats['successes']} | "
            f"{sr} | {a2a} | {a2f} | {f2a} | {files} | {shares} | "
            f"{wall} | {topup} |")
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
    lines.append("## Pre-registered hypothesis results")
    lines.append("")
    if hypothesis_results:
        lines.append("| hypothesis | status | details |")
        lines.append("|---|---|---|")
        for label, status, details in hypothesis_results:
            lines.append(f"| {label} | {status} | {details} |")
    else:
        lines.append("Hypothesis tests not yet runnable.")

    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- The pre-registered analysis plan is at "
                 "`memory/experiments/family-2-full/analysis-plan.md`.")
    lines.append("- Wilson 95 per cent intervals are used for success-rate "
                 "precision.")
    lines.append("- CV is `sd / mean`; metrics with cell mean below 1 are "
                 "excluded from the CV check.")
    lines.append("- target_kind shares are pooled across the cell's runs; "
                 "shares may not sum to 100% due to rounding.")
    lines.append("- Hypothesis test statuses: `confirmed` / `refuted` / "
                 "`inconclusive` / `pending` (data not yet sufficient) / "
                 "`ready` (data sufficient; inference deferred to "
                 "end-of-collection) / `manual` (assessed by inspection).")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Family 2 full schedule preliminary analysis.")
    parser.add_argument(
        "--experiment-root", default="data/family-2-full")
    parser.add_argument(
        "--output",
        default="memory/experiments/family-2-full/preliminary.md")
    parser.add_argument(
        "--h7-census", action="store_true",
        help="re-run each failing conflicting verifier to confirm the exact "
             "two-test H7 footprint identity (slow: one pytest per failure)")
    args = parser.parse_args()

    runs_root = os.path.join(args.experiment_root, "runs")
    master_dir = os.path.join(args.experiment_root, "master")
    runs_csv = os.path.join(master_dir, "runs.csv")
    edges_csv = os.path.join(master_dir, "edges.csv")
    ledger_json = os.path.join(args.experiment_root, "ledger.json")

    # Rebuild master from per-run datasets so the analysis runs on fresh
    # aggregate while the batch is still in flight.
    if os.path.isdir(runs_root):
        per_run = sorted(
            d for d in glob.glob(os.path.join(runs_root, "*", "datasets"))
            if os.path.isdir(d))
        if per_run:
            combine_datasets(per_run, master_dir)

    if not os.path.exists(runs_csv):
        print(f"runs.csv not found at {runs_csv}; nothing to analyse.")
        sys.exit(0)

    ok_run_ids = load_ok_run_ids(ledger_json)
    rows, dropped = load_runs(runs_csv, ok_run_ids=ok_run_ids)
    edge_rows = load_edges(edges_csv, ok_run_ids=ok_run_ids)
    edges_by_runid = defaultdict(list)
    for e in edge_rows:
        edges_by_runid[e["run_id"]].append(e)
    groups = group_by_cell_pattern_task(rows)
    summary = read_ledger_summary(ledger_json)
    if summary is not None:
        summary["ghost_rows_dropped"] = dropped

    hypothesis_results = _hypothesis_results(
        rows, edges_by_runid, experiment_root=args.experiment_root,
        h7_identity_census=args.h7_census)

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    render_report(summary, groups, edges_by_runid,
                  hypothesis_results, args.output)
    print(f"wrote {args.output}")

    if summary:
        print(f"ledger: {summary['ok']} ok, {summary['error']} error, "
              f"{summary['succeeded']} succeeded, {summary['failed']} failed")
    if dropped:
        print(f"ghost rows dropped from runs.csv (not in ledger ok set): "
              f"{dropped}")
    print(f"cell-and-pattern-and-task combinations observed: {len(groups)}")
    full_n = sum(1 for v in groups.values() if len(v) >= PRE_REGISTERED_N)
    print(f"combinations with N >= {PRE_REGISTERED_N}: {full_n}")


if __name__ == "__main__":
    main()
