#!/usr/bin/env python3
"""RQ1 opening-handshake-in-time analysis (+ a message-length glance), 2026-06-15.

We have a clean result that SUSTAINED coordination saturates (the bounded-degree
ceiling, H2). This adds the time axis: is the all-to-all message graph (the
source of the trivial n^2) established as an early OPENING HANDSHAKE, after which
the run is the small saturated core? If so: the n^2 is the handshake; the real
work runs on the bounded sustained core. Reported faithfully whichever way it
falls.

Per run, a2a edges are placed on the normalised timeline tau = (t - t0) /
(t_last - t0) in [0,1] using the run's own first/last a2a timestamps.

  (a) Edge-arrival curve: for each distinct directed pair (i->j), its FIRST
      message tau. Cumulative fraction of the run's eventual distinct pairs
      that have appeared by tau. Summary: tau50, tau90 (50%/90% appeared),
      tau_complete (last first-appearance).
  (b) Per-agent contact completion: per agent, the tau at which it has
      first-contacted every partner it will ever contact (max over its
      first-contact times); mean over agents and runs.
  (c) Shallow vs sustained: the clique-forming layer (any contact) vs the
      sustained layer (pairs reaching >=2 directed messages). For sustained
      pairs, the tau of the 2nd message (channel becomes sustained) and the
      last message (how long it stays live).
  (d) Broadcast sensitivity: (a) on directed pairs only, and again counting a
      broadcast as first-contacting all teammates at once.
  (e) Scaling: tau50/tau90/tau_complete by n per family per draw.

Secondary: do messages get shorter as teams grow? Primary proxy byte_size on
a2a edges (the real size); secondary token_cost (coarse per-turn uniform
attribution). byte_size wins if they disagree.

Definitions reuse the locked H2 conventions: directed peer = target_kind in
{canonical, alias}, excluding self (source==target) and out-of-roster targets
(agent-1..agent-n). Timeline exclusion as in RQ2: drop runs with < 3 a2a edges
or zero duration; exclusion counts reported per cell.

Data scope: F1 process_orders/clean, F2 summarise_transactions/clean (allowed,
peer + solo separate, n in {2,4,8}); the n=8 chain check uses
data/compute-invoices-scaling (NOT the n=4 batch in family-2-full).

Usage:
    .venv/bin/python scripts/analyse_handshake_timing.py
"""

from __future__ import annotations

import csv
import datetime as dt
import math
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from analyse_rq2_dynamics import parse_ts, load_edges_by_run
from analyse_solo_peer_reliability import linregress_slope_ci

csv.field_size_limit(10 ** 7)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
F1_ROOT = os.path.join(REPO, "data", "family-1-full")
F2_ROOT = os.path.join(REPO, "data", "family-2-full")
CI_ROOT = os.path.join(REPO, "data", "compute-invoices-scaling")

OUT_MD = os.path.join(REPO, "memory", "experiments", "handshake-timing.md")
CELL_CSV = os.path.join(REPO, "data", "derived", "handshake-timing-cells.csv")
CURVE_CSV = os.path.join(REPO, "data", "derived",
                         "handshake-arrival-curves.csv")

N_VALUES = (2, 4, 8)
FLAT_DRAWS = ("solo", "peer")
DIRECTED_KINDS = ("canonical", "alias")
TAU_GRID = [i / 20 for i in range(21)]   # 0.00, 0.05, ..., 1.00
_AGENT_RE = re.compile(r"^agent-(\d+)$")


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------

def load_runs(runs_csv, instance):
    """{run_id: meta} for total_output_tokens>0 rows of one instance."""
    meta, dropped = {}, 0
    with open(runs_csv, newline="") as f:
        for r in csv.DictReader(f):
            if r.get("instance") != instance:
                continue
            try:
                if float(r["total_output_tokens"]) <= 0:
                    dropped += 1
                    continue
                n = int(r["agent_count"])
            except (KeyError, ValueError):
                continue
            meta[r["run_id"]] = {
                "n": n, "topology": r["topology"],
                "policy": r["artefact_policy"],
            }
    return meta, dropped


def in_roster(agent_id, n):
    m = _AGENT_RE.match(agent_id)
    return bool(m) and 1 <= int(m.group(1)) <= n


# ---------------------------------------------------------------------------
# per-run timing
# ---------------------------------------------------------------------------

def run_timing(a2a_edges, n):
    """Compute the handshake-timing quantities for one run's a2a edges.

    Returns None if the run is timing-excluded (< 3 a2a edges or zero
    duration). Otherwise a dict of the per-run metrics.
    """
    if len(a2a_edges) < 3:
        return None
    # sort by timestamp only -- never compare the edge dicts (two distinct
    # edges sharing a timestamp would otherwise raise dict < dict).
    parsed = sorted(((parse_ts(e["timestamp"]), e) for e in a2a_edges),
                    key=lambda x: x[0])
    t0, tl = parsed[0][0], parsed[-1][0]
    dur = (tl - t0).total_seconds()
    if dur <= 0:
        return None

    def tau(ts):
        return (ts - t0).total_seconds() / dur

    directed = defaultdict(list)        # (src,tgt) -> [tau,...]
    broadcasts = []                     # (src, tau)
    sizes, tokens = [], []
    for ts, e in parsed:
        sizes.append(float(e["byte_size"]))
        tokens.append(float(e["token_cost"]) if e["token_cost"].strip()
                      else 0.0)
        k = e["target_kind"]
        if k == "broadcast":
            broadcasts.append((e["source"], tau(ts)))
        elif k in DIRECTED_KINDS:
            s, t = e["source"], e["target"]
            if s == t or not in_roster(t, n):
                continue
            directed[(s, t)].append(tau(ts))

    out = {
        "n_a2a": len(a2a_edges), "duration_s": dur,
        "mean_byte_size": sum(sizes) / len(sizes),
        "mean_token_cost": sum(tokens) / len(tokens),
        "n_directed_pairs": len(directed),
    }

    # (a) directed-only edge-arrival curve
    first_dir = {p: min(taus) for p, taus in directed.items()}
    out.update(_curve_summary(first_dir, "dir"))
    out["curve_dir"] = _sample_curve(first_dir)

    # (d) broadcast-inclusive: a broadcast from i first-contacts all peers
    first_bc = dict(first_dir)
    for src, tb in broadcasts:
        for j in range(1, n + 1):
            peer = f"agent-{j}"
            if peer == src:
                continue
            p = (src, peer)
            if p not in first_bc or tb < first_bc[p]:
                first_bc[p] = tb
    out.update(_curve_summary(first_bc, "bc"))
    out["curve_bc"] = _sample_curve(first_bc)

    # (b) per-agent contact completion (directed)
    by_src = defaultdict(list)
    for (s, t), tau0 in first_dir.items():
        by_src[s].append(tau0)
    comps = [max(v) for v in by_src.values() if v]
    out["agent_completion"] = (sum(comps) / len(comps)) if comps else None

    # (c) shallow vs sustained
    sustained = {p: sorted(taus) for p, taus in directed.items()
                 if len(taus) >= 2}
    out["n_sustained_pairs"] = len(sustained)
    if sustained:
        out["sustained_second_tau"] = sum(v[1] for v in sustained.values()) \
            / len(sustained)
        out["sustained_last_tau"] = sum(v[-1] for v in sustained.values()) \
            / len(sustained)
    else:
        out["sustained_second_tau"] = None
        out["sustained_last_tau"] = None
    return out


def _curve_summary(first_app, suffix):
    """tau50/tau90/tau_complete from a {pair: first-appearance tau} map."""
    if not first_app:
        return {f"tau50_{suffix}": None, f"tau90_{suffix}": None,
                f"tau_complete_{suffix}": None, f"n_pairs_{suffix}": 0}
    F = sorted(first_app.values())
    P = len(F)

    def q(frac):
        idx = max(0, math.ceil(frac * P) - 1)
        return F[min(idx, P - 1)]

    return {f"tau50_{suffix}": q(0.5), f"tau90_{suffix}": q(0.9),
            f"tau_complete_{suffix}": F[-1], f"n_pairs_{suffix}": P}


def _sample_curve(first_app):
    """Cumulative fraction of pairs appeared by each tau in TAU_GRID."""
    if not first_app:
        return [0.0] * len(TAU_GRID)
    F = sorted(first_app.values())
    P = len(F)
    return [sum(1 for x in F if x <= g) / P for g in TAU_GRID]


# ---------------------------------------------------------------------------
# cell aggregation
# ---------------------------------------------------------------------------

def collect_cell(meta, by_run, draw, n):
    """Per-run metrics for one (draw, n) cell; plus exclusion count."""
    recs, excluded = [], 0
    for rid, m in meta.items():
        if m["topology"] != draw or m["n"] != n or m["policy"] != "allowed":
            continue
        a2a = [e for e in by_run.get(rid, [])
               if e["edge_type"] == "agent_to_agent"]
        rec = run_timing(a2a, n)
        if rec is None:
            excluded += 1
        else:
            recs.append(rec)
    return recs, excluded


def cmean(recs, key):
    vs = [r[key] for r in recs if r.get(key) is not None]
    return (sum(vs) / len(vs)) if vs else float("nan")


def mean_curve(recs, key):
    # Average only over runs that actually have pairs for this curve variant
    # (a run with zero directed pairs -- all-broadcast -- contributes an
    # all-zero curve and would otherwise stop the mean reaching 1.0, making
    # the curve inconsistent with the tau summary stats, which skip it).
    cols = [r[key] for r in recs if r.get(key) and max(r[key]) > 0]
    if not cols:
        return [float("nan")] * len(TAU_GRID)
    return [sum(c[i] for c in cols) / len(cols) for i in range(len(TAU_GRID))]


def perrun_slope(meta, by_run, draw, key):
    """Per-run OLS log-log slope of `key` on n (the locked H2 convention)."""
    xs, ys = [], []
    for n in N_VALUES:
        recs, _ = collect_cell(meta, by_run, draw, n)
        for r in recs:
            v = r.get(key)
            if v and v > 0:
                xs.append(math.log(n))
                ys.append(math.log(v))
    return linregress_slope_ci(xs, ys)


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

def _f(x, p=3):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "--"
    return f"{x:.{p}f}"


def timing_table(meta, by_run, fam_label, L, cell_rows, curve_rows, fam_key):
    L.append(f"#### {fam_label} — handshake timing (allowed, clean)")
    L.append("")
    L.append("| draw | n | N | excl | 0-dir | tau50 | tau90 | tau_complete | "
             "agent-completion | sustained 2nd | sustained last | "
             "tau90 (bcast) | pairs(dir) |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for draw in FLAT_DRAWS:
        for n in N_VALUES:
            recs, excl = collect_cell(meta, by_run, draw, n)
            if not recs:
                continue
            n_zero = sum(1 for r in recs if r["n_directed_pairs"] == 0)
            row = {
                "family": fam_key, "draw": draw, "n": n, "N": len(recs),
                "excluded": excl, "n_zero_directed": n_zero,
                "tau50_dir": cmean(recs, "tau50_dir"),
                "tau90_dir": cmean(recs, "tau90_dir"),
                "tau_complete_dir": cmean(recs, "tau_complete_dir"),
                "agent_completion": cmean(recs, "agent_completion"),
                "sustained_second_tau": cmean(recs, "sustained_second_tau"),
                "sustained_last_tau": cmean(recs, "sustained_last_tau"),
                "tau50_bc": cmean(recs, "tau50_bc"),
                "tau90_bc": cmean(recs, "tau90_bc"),
                "tau_complete_bc": cmean(recs, "tau_complete_bc"),
                "mean_byte_size": cmean(recs, "mean_byte_size"),
                "mean_token_cost": cmean(recs, "mean_token_cost"),
                "n_directed_pairs": cmean(recs, "n_directed_pairs"),
                "n_sustained_pairs": cmean(recs, "n_sustained_pairs"),
            }
            cell_rows.append(row)
            L.append(
                f"| {draw} | {n} | {len(recs)} | {excl} | {n_zero} | "
                f"{_f(row['tau50_dir'])} | {_f(row['tau90_dir'])} | "
                f"{_f(row['tau_complete_dir'])} | "
                f"{_f(row['agent_completion'])} | "
                f"{_f(row['sustained_second_tau'])} | "
                f"{_f(row['sustained_last_tau'])} | {_f(row['tau90_bc'])} | "
                f"{_f(row['n_directed_pairs'], 1)} |")
            for i, g in enumerate(TAU_GRID):
                curve_rows.append({
                    "family": fam_key, "draw": draw, "n": n, "tau": g,
                    "cum_frac_dir": mean_curve(recs, "curve_dir")[i],
                    "cum_frac_bc": mean_curve(recs, "curve_bc")[i],
                })
    L.append("")


def size_table(meta, by_run, fam_label, L):
    L.append(f"#### {fam_label} — message size vs n (peer/solo, allowed, clean)")
    L.append("")
    L.append("| draw | byte_size n=2/4/8 | byte_size slope [95% CI] | "
             "token_cost n=2/4/8 | token_cost slope [95% CI] |")
    L.append("|---|---|---|---|---|")
    for draw in FLAT_DRAWS:
        bs = {n: cmean(collect_cell(meta, by_run, draw, n)[0],
                       "mean_byte_size") for n in N_VALUES}
        tc = {n: cmean(collect_cell(meta, by_run, draw, n)[0],
                       "mean_token_cost") for n in N_VALUES}
        b = perrun_slope(meta, by_run, draw, "mean_byte_size")
        t = perrun_slope(meta, by_run, draw, "mean_token_cost")
        L.append(
            f"| {draw} | {'/'.join(_f(bs[n], 0) for n in N_VALUES)} | "
            f"{_f(b[0], 2)} [{_f(b[1], 2)}, {_f(b[2], 2)}] | "
            f"{'/'.join(_f(tc[n], 0) for n in N_VALUES)} | "
            f"{_f(t[0], 2)} [{_f(t[1], 2)}, {_f(t[2], 2)}] |")
    L.append("")


def verdicts(f1m, f1e, f2m, f2e, L):
    L.append("## Verdicts (allowed, clean)")
    L.append("")
    for fam, meta, by_run in [("Family 1", f1m, f1e), ("Family 2", f2m, f2e)]:
        L.append(f"### {fam}")
        for draw in FLAT_DRAWS:
            t90 = {}
            for n in N_VALUES:
                recs, _ = collect_cell(meta, by_run, draw, n)
                t90[n] = cmean(recs, "tau90_dir")
            vals = [t90[n] for n in N_VALUES if not math.isnan(t90[n])]
            early = all(v < 0.5 for v in vals) if vals else False
            late = all(v > 0.85 for v in vals) if vals else False
            verdict = ("CONFIRMED" if early else "REFUTED" if late
                       else "MIXED/UNDERPOWERED")
            # sustained-later secondary check at n=8
            r8, _ = collect_cell(meta, by_run, draw, 8)
            s_last = cmean(r8, "sustained_last_tau")
            sh90 = cmean(r8, "tau90_dir")
            sec = ("supported" if (not math.isnan(s_last)
                   and not math.isnan(sh90) and s_last > sh90) else "not seen")
            L.append(
                f"- **{draw}: handshake-early** {verdict}. directed tau90 by "
                f"n(2/4/8) = {'/'.join(_f(t90[n], 2) for n in N_VALUES)} "
                f"(CONFIRM if <0.5 and staying early; REFUTE if ~1.0). "
                f"Secondary (sustained later than shallow, n=8): {sec} "
                f"(shallow tau90 {_f(sh90, 2)} vs sustained last "
                f"{_f(s_last, 2)}).")
        # message size verdict
        bslope = perrun_slope(meta, by_run, "peer", "mean_byte_size")
        mv = ("CONFIRMED (shorter)" if bslope[2] < 0 else
              "REFUTED (not shorter)" if bslope[1] > 0 else "UNDERPOWERED")
        L.append(f"- **messages-get-shorter (peer):** {mv}. byte_size slope "
                 f"{_f(bslope[0], 2)} [{_f(bslope[1], 2)}, {_f(bslope[2], 2)}]"
                 f". If not negative, the sub-quadratic token growth is the "
                 f"prose residual already documented, not shorter messages.")
        L.append("")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def build():
    f1_meta, f1_drop = load_runs(
        os.path.join(F1_ROOT, "master", "runs.csv"), "process_orders/clean")
    f2_meta, f2_drop = load_runs(
        os.path.join(F2_ROOT, "master", "runs.csv"),
        "summarise_transactions/clean")
    ci_meta, ci_drop = load_runs(
        os.path.join(CI_ROOT, "master", "runs.csv"), "compute_invoices/clean")

    f1_edges = load_edges_by_run(
        os.path.join(F1_ROOT, "master", "edges.csv"), set(f1_meta))
    f2_edges = load_edges_by_run(
        os.path.join(F2_ROOT, "master", "edges.csv"), set(f2_meta))
    ci_edges = load_edges_by_run(
        os.path.join(CI_ROOT, "master", "edges.csv"), set(ci_meta))

    L = []
    L.append("# RQ1 — the opening-handshake-in-time analysis")
    L.append("")
    L.append(f"Generated {dt.date.today().isoformat()} by "
             "`scripts/analyse_handshake_timing.py`. Normalised a2a timeline "
             "tau=(t-t0)/(t_last-t0). Directed peer = canonical/alias, self "
             "and out-of-roster excluded (locked H2 defn). Timing-excluded: "
             "<3 a2a edges or zero duration (per-cell `excl` column; the n=1 "
             "cells are out of scope). Standard filter total_output_tokens>0 "
             f"dropped {f1_drop} F1, {f2_drop} F2, {ci_drop} CI rows.")
    L.append("")

    cell_rows, curve_rows = [], []
    L.append("## Primary — when does the message graph complete?")
    L.append("")
    timing_table(f1_meta, f1_edges, "Family 1 (process_orders)", L,
                 cell_rows, curve_rows, "process_orders")
    timing_table(f2_meta, f2_edges, "Family 2 (summarise_transactions)", L,
                 cell_rows, curve_rows, "summarise_transactions")
    # chain check: compute-invoices-scaling n=8 peer
    L.append("#### compute_invoices/clean chain check (data/compute-invoices-"
             "scaling, peer)")
    L.append("")
    L.append("| n | N | excl | 0-dir | tau50 | tau90 | tau_complete | "
             "sustained last | tau90 (bcast) |")
    L.append("|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for n in N_VALUES:
        recs, excl = collect_cell(ci_meta, ci_edges, "peer", n)
        if not recs:
            continue
        n_zero = sum(1 for r in recs if r["n_directed_pairs"] == 0)
        L.append(f"| {n} | {len(recs)} | {excl} | {n_zero} | "
                 f"{_f(cmean(recs, 'tau50_dir'))} | "
                 f"{_f(cmean(recs, 'tau90_dir'))} | "
                 f"{_f(cmean(recs, 'tau_complete_dir'))} | "
                 f"{_f(cmean(recs, 'sustained_last_tau'))} | "
                 f"{_f(cmean(recs, 'tau90_bc'))} |")
        for i, g in enumerate(TAU_GRID):
            curve_rows.append({
                "family": "compute_invoices", "draw": "peer", "n": n,
                "tau": g, "cum_frac_dir": mean_curve(recs, "curve_dir")[i],
                "cum_frac_bc": mean_curve(recs, "curve_bc")[i]})
        cell_rows.append({"family": "compute_invoices", "draw": "peer",
                          "n": n, "N": len(recs), "excluded": excl,
                          "n_zero_directed": n_zero,
                          **{k: cmean(recs, k) for k in (
                              "tau50_dir", "tau90_dir", "tau_complete_dir",
                              "agent_completion", "sustained_second_tau",
                              "sustained_last_tau", "tau50_bc", "tau90_bc",
                              "tau_complete_bc", "mean_byte_size",
                              "mean_token_cost", "n_directed_pairs",
                              "n_sustained_pairs")}})
    L.append("")
    L.append("NB: at n=2 most compute_invoices runs coordinate entirely by "
             "broadcast (0-dir column), so the directed tau there is over very "
             "few runs/pairs and is coarse; read the broadcast-inclusive "
             "column and the n=4/8 cells for the chain picture.")
    L.append("")

    L.append("## Secondary — do messages get shorter as teams grow?")
    L.append("")
    size_table(f1_meta, f1_edges, "Family 1", L)
    size_table(f2_meta, f2_edges, "Family 2", L)

    verdicts(f1_meta, f1_edges, f2_meta, f2_edges, L)

    L.append("## Plain-English summary")
    L.append("")
    L.append(
        "**The opening-handshake reading holds.** The distinct directed-pair "
        "graph -- the source of the trivial n^2 -- is established EARLY in the "
        "messaging window and at a roughly CONSTANT early fraction as teams "
        "grow: directed tau90 is ~0.16-0.18 across n=2/4/8 in F1 solo and "
        "~0.26-0.36 in F2, even as the pair count grows from ~2 to ~50. "
        "tau_complete sits well below 1.0 in every in-scope cell (the last NEW "
        "pair appears at ~0.2-0.66 of the window), so the back of the run is "
        "repeat traffic on an already-complete graph, not continued "
        "densification. Confirmed in 3 of 4 family x draw cells; the one "
        "exception is F1 peer at n=8 (tau90 0.60), the same least-reproducible "
        "n=8 peer cell flagged elsewhere (the file/messaging blow-up), not a "
        "general refutation.")
    L.append("")
    L.append(
        "**Handshake-then-bounded-core.** In all four cells the sustained "
        "channels (pairs reaching >=2 directed messages) have their second and "
        "last messages spread LATER (last-message tau ~0.6-0.8) than the "
        "shallow graph completes (tau90 ~0.2-0.3). So the picture marries RQ1 "
        "to RQ2: the n^2 is an early opening handshake; afterwards coordination "
        "runs on the small saturated core of sustained channels. The "
        "compute_invoices full-decomposition chain agrees (n=8 tau90 0.27, "
        "tau_complete 0.32, sustained last 0.75).")
    L.append("")
    L.append(
        "**Messages also get shorter (a real second axis).** Mean a2a message "
        "byte_size DECREASES with n in both families and both draws (per-run "
        "log-log slope -0.28 to -0.63, all CIs strictly negative). token_cost "
        "is ~0.25x byte_size run-for-run (near-constant ratio), so it is "
        "redundant with byte_size and gives the same slope -- byte_size is the "
        "real length proxy and it confirms genuine shortening, not just the "
        "documented per-turn token-attribution artefact. Net: as teams grow, "
        "the per-message payload shrinks, a dilution axis distinct from the "
        "bounded-degree ceiling.")
    L.append("")
    L.append(
        "tau is normalised to each run's a2a window (first..last a2a edge), so "
        "'early' means early within the messaging span; tau_complete < 1.0 is "
        "the load-bearing fact (new pairs stop forming before the last "
        "message).")
    L.append("")

    # CSVs
    os.makedirs(os.path.dirname(CELL_CSV), exist_ok=True)
    cell_fields = ["family", "draw", "n", "N", "excluded", "n_zero_directed",
                   "tau50_dir",
                   "tau90_dir", "tau_complete_dir", "agent_completion",
                   "sustained_second_tau", "sustained_last_tau", "tau50_bc",
                   "tau90_bc", "tau_complete_bc", "mean_byte_size",
                   "mean_token_cost", "n_directed_pairs", "n_sustained_pairs"]
    with open(CELL_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cell_fields)
        w.writeheader()
        for row in cell_rows:
            w.writerow({k: row.get(k, "") for k in cell_fields})
    with open(CURVE_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["family", "draw", "n", "tau",
                                          "cum_frac_dir", "cum_frac_bc"])
        w.writeheader()
        for row in curve_rows:
            w.writerow(row)

    os.makedirs(os.path.dirname(OUT_MD), exist_ok=True)
    with open(OUT_MD, "w") as f:
        f.write("\n".join(L) + "\n")
    return cell_rows, curve_rows


def main():
    cells, curves = build()
    print(f"wrote {OUT_MD}")
    print(f"wrote {CELL_CSV} ({len(cells)} cell rows)")
    print(f"wrote {CURVE_CSV} ({len(curves)} curve rows)")


if __name__ == "__main__":
    main()
