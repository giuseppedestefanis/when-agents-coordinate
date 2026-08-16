#!/usr/bin/env python3
"""Solo-vs-peer reliability analysis (2026-06-10).

At n>=2, the "solo" and "peer" topologies are the SAME configuration:
identical prompts, identical message-protocol MCP wiring, identical launch
path (only the orchestrator topology adds a coordinator clause). See
`memory/experiments/solo-equals-peer-finding.md`. The solo and peer cells of
each matched (n, policy, pattern) were nonetheless collected in different
sessions, so the solo-vs-peer comparison is an accidental test-retest
reliability probe: same configuration, different session, same pinned model.

This script quantifies three things the paper needs:

  A. Reliability / drift table: per matched cell, solo vs peer means and a
     Mann-Whitney / Fisher test, plus an aggregate "how often do two draws of
     the same configuration differ significantly" number.

  B. RQ1 robustness: the agent-count scaling slope (log-log over per-run a2a)
     under peer-only (current paper), solo-only, and pooled-flat, for both
     families. Tells the writer whether the n^2 result and the n=4 break
     survive the arbitrary solo/peer choice.

  C. RQ3 robustness: the orchestrator-vs-flat verifier-success contrast at
     n=4 and n=8, where flat = solo POOLED with peer (N=20), instead of the
     current orchestrator-vs-peer (N=10). Tells the writer whether the
     coordinator-helps-at-n=4 / reverses-at-n=8 story survives the reframing.

Usage:
    .venv/bin/python scripts/analyse_solo_peer_reliability.py
"""

from __future__ import annotations

import csv
import datetime as dt
import math
import os
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # sibling scripts

# Ties-safe exact permutation Mann-Whitney (full enumeration of the U
# statistic), reused from the pilot script. At the matched cells' N=10 vs N=10
# this enumerates C(20,10)=184,756 assignments per cell (~1.5 s/cell).
from analyse_pilot import exact_mannwhitney_p

# RQ2 temporal-shape code, reused so the §5.6 per-draw decile profiles use the
# exact same definition as the RQ2 dynamics figure (per-run decile fractions,
# averaged; <3-edge / zero-duration runs excluded).
from analyse_rq2_dynamics import (run_metrics, mean_profile,
                                   load_edges_by_run, load_ok_run_ids,
                                   parse_run_id as rq2_parse_run_id)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
F1_ROOT = os.path.join(REPO, "data", "family-1-full")
F2_ROOT = os.path.join(REPO, "data", "family-2-full")
F1_CSV = os.path.join(F1_ROOT, "master", "runs.csv")
F2_CSV = os.path.join(F2_ROOT, "master", "runs.csv")
F1_TURNS = os.path.join(F1_ROOT, "master", "turns.csv")
F2_TURNS = os.path.join(F2_ROOT, "master", "turns.csv")
OUT = os.path.join(REPO, "memory", "experiments", "solo-peer-reliability.md")
SCATTER_CSV = os.path.join(REPO, "memory", "experiments",
                           "solo-peer-scatter-data.csv")

# Per-cell scatter rows for the reliability figure (writer renders into paper/).
SCATTER_ROWS = []

PATTERNS = ("clean", "overlapping", "conflicting")
POLICIES = ("forbidden", "allowed", "mandatory")
N_VALUES = (2, 4, 8)


# ---------- small stats helpers (pure python, no scipy) ----------

def mean(v):
    return sum(v) / len(v) if v else float("nan")


def sd(v):
    if len(v) < 2:
        return float("nan")
    m = mean(v)
    return math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1))


def norm_cdf(z):
    t = 1.0 / (1.0 + 0.2316419 * abs(z))
    poly = t * (0.319381530 + t * (-0.356563782 + t * (1.781477937
               + t * (-1.821255978 + t * 1.330274429))))
    p_up = poly * math.exp(-0.5 * z * z) / math.sqrt(2 * math.pi)
    return p_up if z < 0 else 1.0 - p_up


def mannwhitney_p(xs, ys):
    nx, ny = len(xs), len(ys)
    if nx == 0 or ny == 0:
        return float("nan")
    comb = sorted([(v, 0) for v in xs] + [(v, 1) for v in ys])
    ranks = [0.0] * (nx + ny)
    i = 0
    while i < len(comb):
        j = i
        while j < len(comb) and comb[j][0] == comb[i][0]:
            j += 1
        mid = (i + j + 1) / 2.0
        for k in range(i, j):
            ranks[k] = mid
        i = j
    tie = 0.0
    i = 0
    while i < len(comb):
        j = i
        while j < len(comb) and comb[j][0] == comb[i][0]:
            j += 1
        t = j - i
        if t > 1:
            tie += t ** 3 - t
        i = j
    rx = sum(ranks[k] for k in range(len(comb)) if comb[k][1] == 0)
    ux = rx - nx * (nx + 1) / 2
    u = min(ux, nx * ny - ux)
    nt = nx + ny
    mu = nx * ny / 2
    var = (nx * ny / (nt * (nt - 1))) * ((nt ** 3 - nt) / 12 - tie / 12)
    if var <= 0:
        return float("nan")
    z = (u - mu) / math.sqrt(var)
    return 2 * norm_cdf(-abs(z))


def linregress_slope_ci(xs, ys):
    """OLS slope of y on x with 95% CI (t approx, df=n-2)."""
    n = len(xs)
    if n < 3:
        return (float("nan"),) * 3
    mx, my = mean(xs), mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    if sxx == 0:
        return (float("nan"),) * 3
    b = sxy / sxx
    a = my - b * mx
    sse = sum((y - (a + b * x)) ** 2 for x, y in zip(xs, ys))
    s2 = sse / (n - 2)
    se = math.sqrt(s2 / sxx)
    # t ~ 2.0 for the df we have (28+); use cornish-fisher-ish 1.96 inflation
    tcrit = 1.96 + 2.4 / max(1, n - 2)
    return (b, b - tcrit * se, b + tcrit * se)


# ---------- load ----------

def load(path):
    rows = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            inst = r.get("instance", "")
            task = inst.split("/")[0] if "/" in inst else inst
            patt = inst.split("/")[1] if "/" in inst else ""
            try:
                n = int(r["agent_count"])
            except (KeyError, ValueError):
                continue
            rec = {
                "task": task, "pattern": patt, "n": n,
                "topology": r["topology"], "policy": r["artefact_policy"],
                "success": r.get("success", "").lower() == "true",
            }
            for k in ("n_agent_to_agent", "n_file_nodes",
                      "total_output_tokens", "completion_time_s"):
                try:
                    rec[k] = float(r[k])
                except (KeyError, ValueError, TypeError):
                    rec[k] = float("nan")
            rows.append(rec)
    return rows


def cell(rows, task, n, topo, pol, patt):
    return [r for r in rows if r["task"] == task and r["n"] == n
            and r["topology"] == topo and r["policy"] == pol
            and r["pattern"] == patt]


# ---------- A. reliability table ----------

def reliability(rows, task, lines):
    lines.append(f"### {task} — solo vs peer (same config, different session)")
    lines.append("")
    lines.append("| n | policy | pattern | solo a2a | peer a2a | ratio | "
                 "MW p (approx) | sig | exact p | exact sig | "
                 "solo succ | peer succ |")
    lines.append("|---|---|---|---:|---:|---:|---:|:--:|---:|:--:|---:|---:|")
    n_cells = 0
    n_sig = 0
    n_sig_exact = 0
    ratios = []
    for n in N_VALUES:
        for pol in POLICIES:
            for patt in PATTERNS:
                s = cell(rows, task, n, "solo", pol, patt)
                p = cell(rows, task, n, "peer", pol, patt)
                if len(s) < 5 or len(p) < 5:
                    continue
                sa = [r["n_agent_to_agent"] for r in s
                      if not math.isnan(r["n_agent_to_agent"])]
                pa = [r["n_agent_to_agent"] for r in p
                      if not math.isnan(r["n_agent_to_agent"])]
                sm, pm = mean(sa), mean(pa)
                mwp = mannwhitney_p(sa, pa)
                exactp = exact_mannwhitney_p(sa, pa)[0]
                ratio = (sm / pm) if pm > 0 else float("inf")
                ssucc = sum(r["success"] for r in s)
                psucc = sum(r["success"] for r in p)
                n_cells += 1
                sig = (not math.isnan(mwp)) and mwp < 0.05
                sig_exact = (not math.isnan(exactp)) and exactp < 0.05
                if sig:
                    n_sig += 1
                if sig_exact:
                    n_sig_exact += 1
                if pm > 0 and sm > 0:
                    ratios.append(max(sm, pm) / min(sm, pm))
                SCATTER_ROWS.append({
                    "family": task, "n": n, "policy": pol, "pattern": patt,
                    "peer_a2a": f"{pm:.3f}", "solo_a2a": f"{sm:.3f}",
                    "mw_p": f"{mwp:.4f}", "significant": int(sig),
                    "exact_p": f"{exactp:.4f}",
                    "exact_significant": int(sig_exact),
                })
                lines.append(
                    f"| {n} | {pol} | {patt} | {sm:.1f} | {pm:.1f} | "
                    f"{ratio:.2f} | {mwp:.3f} | {'*' if sig else ''} | "
                    f"{exactp:.3f} | {'*' if sig_exact else ''} | "
                    f"{ssucc}/{len(s)} | {psucc}/{len(p)} |")
    lines.append("")
    if n_cells:
        lines.append(
            f"**{task} summary:** {n_sig}/{n_cells} matched cells differ "
            f"significantly under the tie-corrected normal approximation "
            f"(MW p<0.05); {n_sig_exact}/{n_cells} under the exact permutation "
            f"test. Same configuration, different session. Median "
            f"fold-difference in cell-mean a2a = "
            f"{sorted(ratios)[len(ratios)//2]:.2f}x (max {max(ratios):.2f}x).")
    lines.append("")
    return n_cells, n_sig, n_sig_exact


# ---------- B. RQ1 scaling robustness ----------

def scaling_slope(rows, task, topos, patt="clean", pol="allowed"):
    """Per-run log-log slope of a2a on n, pooling the given topologies."""
    xs, ys = [], []
    seg = {}
    for n in N_VALUES:
        vals = []
        for topo in topos:
            for r in cell(rows, task, n, topo, pol, patt):
                a = r["n_agent_to_agent"]
                if a and a > 0 and not math.isnan(a):
                    vals.append(a)
        for a in vals:
            xs.append(math.log(n))
            ys.append(math.log(a))
        seg[n] = mean(vals)
    slope = linregress_slope_ci(xs, ys)
    # two-point segment descriptors on cell means
    d24 = (math.log(seg[4]) - math.log(seg[2])) / (math.log(4) - math.log(2)) \
        if seg.get(2) and seg.get(4) else float("nan")
    d48 = (math.log(seg[8]) - math.log(seg[4])) / (math.log(8) - math.log(4)) \
        if seg.get(4) and seg.get(8) else float("nan")
    return slope, seg, d24, d48


def rq1_robustness(rows, task, lines):
    lines.append(f"### {task} — RQ1 scaling under peer-only / solo-only / "
                 f"flat-pooled (allowed/clean)")
    lines.append("")
    lines.append("| topology set | slope (95% CI) | mean a2a n=2/4/8 | "
                 "seg 2->4 | seg 4->8 |")
    lines.append("|---|---|---|---:|---:|")
    for label, topos in [("peer only (current paper)", ("peer",)),
                         ("solo only", ("solo",)),
                         ("flat pooled (solo+peer)", ("solo", "peer"))]:
        (b, lo, hi), seg, d24, d48 = scaling_slope(rows, task, topos)
        means = "/".join(f"{seg.get(n, float('nan')):.0f}" for n in N_VALUES)
        lines.append(
            f"| {label} | {b:.2f} [{lo:.2f}, {hi:.2f}] | {means} | "
            f"{d24:.2f} | {d48:.2f} |")
    lines.append("")


# ---------- C. RQ3 orchestrator-vs-flat ----------

def succ_counts(rows, task, n, topos, pol, patt):
    k = nn = 0
    for topo in topos:
        for r in cell(rows, task, n, topo, pol, patt):
            nn += 1
            k += 1 if r["success"] else 0
    return k, nn


def fisher_2x2_p(a, b, c, d):
    """Two-sided Fisher exact p for [[a,b],[c,d]] (small counts)."""
    from math import comb
    n = a + b + c + d
    r1 = a + b
    c1 = a + c
    def hyp(x):
        lo = max(0, c1 - (n - r1))
        hi = min(r1, c1)
        if x < lo or x > hi:
            return 0.0
        return comb(r1, x) * comb(n - r1, c1 - x) / comb(n, c1)
    p_obs = hyp(a)
    lo = max(0, c1 - (n - r1))
    hi = min(r1, c1)
    return sum(hyp(x) for x in range(lo, hi + 1) if hyp(x) <= p_obs + 1e-12)


def rq3_robustness(rows, task, lines):
    lines.append(f"### {task} — RQ3 orchestrator vs flat(solo+peer) success")
    lines.append("")
    lines.append("| n | policy | pattern | orch succ | flat succ | "
                 "(peer-only succ) | Fisher p orch-vs-flat |")
    lines.append("|---|---|---|---:|---:|---:|---:|")
    for n in (4, 8):
        for pol in POLICIES:
            for patt in PATTERNS:
                ko, no = succ_counts(rows, task, n, ("orchestrator",), pol, patt)
                kf, nf = succ_counts(rows, task, n, ("solo", "peer"), pol, patt)
                kp, np_ = succ_counts(rows, task, n, ("peer",), pol, patt)
                if no < 5 or nf < 10:
                    continue
                p = fisher_2x2_p(ko, no - ko, kf, nf - kf)
                lines.append(
                    f"| {n} | {pol} | {patt} | {ko}/{no} | {kf}/{nf} | "
                    f"{kp}/{np_} | {p:.3f} |")
    lines.append("")


# ---------- D. collection-gap timing ----------

def run_start_times(turns_csv):
    """Per-run start time = earliest turn timestamp for the run_id."""
    starts = {}
    if not os.path.exists(turns_csv):
        return starts
    with open(turns_csv, newline="") as f:
        for r in csv.DictReader(f):
            rid, ts = r.get("run_id"), r.get("timestamp")
            if not rid or not ts:
                continue
            try:
                t = dt.datetime.fromisoformat(
                    ts.replace("Z", "+00:00")).timestamp()
            except ValueError:
                continue
            if rid not in starts or t < starts[rid]:
                starts[rid] = t
    return starts


_RUN_RE = __import__("re").compile(
    r"^family-\d+-[a-z_0-9]+"
    r"-(?P<pattern>clean|overlapping|conflicting)"
    r"-a(?P<n>\d+)-(?P<topo>solo|peer|orchestrator)"
    r"-(?P<pol>forbidden|allowed|mandatory)-r\d+$")


def parse_cell_from_run_id(run_id):
    """(n, topology, policy, pattern) for a matched-cell run, else None."""
    m = _RUN_RE.match(run_id)
    if not m:
        return None
    return int(m["n"]), m["topo"], m["pol"], m["pattern"]


def collection_gaps(turns_csv, family_label, lines):
    """§5.5 timing: within-draw spans, per-cell solo-vs-peer collection gap,
    and the interleave (two-block) check, from per-run start times."""
    starts = run_start_times(turns_csv)
    cells = defaultdict(lambda: defaultdict(list))   # (n,pol,patt)->topo->[t]
    for rid, t in starts.items():
        parsed = parse_cell_from_run_id(rid)
        if parsed is None:
            continue
        n, topo, pol, pattern = parsed
        if n < 2:
            continue
        cells[(n, pol, pattern)][topo].append(t)

    within_spans, gaps = [], []
    solo_all, peer_all = [], []
    for ck, byt in cells.items():
        s, p = sorted(byt.get("solo", [])), sorted(byt.get("peer", []))
        if len(s) < 5 or len(p) < 5:
            continue
        within_spans.append((max(s) - min(s)) / 3600.0)
        within_spans.append((max(p) - min(p)) / 3600.0)
        gaps.append(abs(statistics.median(p) - statistics.median(s)) / 3600.0)
        solo_all += s
        peer_all += p

    # Two-block test: are the solo and peer draws two disjoint time blocks, or
    # do their time-ranges overlap (interleave)?
    overlap = (min(solo_all) <= max(peer_all)
               and min(peer_all) <= max(solo_all)) if (solo_all and peer_all) \
        else False
    two_block = not overlap

    lines.append(f"### {family_label} — collection-gap timing")
    lines.append("")
    lines.append(f"- matched cells: {len(gaps)}")
    lines.append(f"- within-draw span (max-min run start across a draw's ten "
                 f"runs), median over {len(within_spans)} draws: "
                 f"**{statistics.median(within_spans):.2f} h**")
    lines.append(f"- per-cell gap |median(peer start) - median(solo start)|, "
                 f"median over {len(gaps)} cells: "
                 f"**{statistics.median(gaps):.2f} h**")
    lines.append(f"- two contiguous blocks? **{two_block}** "
                 f"(solo/peer time-ranges {'overlap' if overlap else 'disjoint'}"
                 f" -> draws {'interleave' if overlap else 'do not interleave'})")
    lines.append("")
    return {"within_median": statistics.median(within_spans),
            "gap_median": statistics.median(gaps), "two_block": two_block}


# ---------- E. per-draw temporal-shape (decile-profile) reliability ----------

EDGE_TYPES = ("a2a", "a2f", "f2a")


def _tokens_map(runs_csv):
    out = {}
    with open(runs_csv, newline="") as f:
        for r in csv.DictReader(f):
            try:
                out[r["run_id"]] = float(r["total_output_tokens"])
            except (KeyError, ValueError, TypeError):
                out[r["run_id"]] = 0.0
    return out


def decile_profile_comparison(root, task, family_label, lines):
    """§5.6: do the temporal activity SHAPES reproduce across the matched
    solo/peer sessions even when message VOLUMES diverge?

    Per draw (solo, peer) pool every multi-agent run (n>=2, total_output_tokens
    > 0, >=3 edges, non-zero duration) of that draw in the family; build the
    mean decile profile per edge type (per-run decile fractions averaged, the
    RQ2-dynamics definition); compare the two draws by the max per-decile
    |solo - peer| per edge type.
    """
    ok = load_ok_run_ids(os.path.join(root, "ledger.json"))
    edges_by_run = load_edges_by_run(
        os.path.join(root, "master", "edges.csv"), ok)
    tokens = _tokens_map(os.path.join(root, "master", "runs.csv"))

    draws = {"solo": [], "peer": []}
    for rid, edges in edges_by_run.items():
        parts = rq2_parse_run_id(rid)
        if (parts is None or parts["task"] != task
                or parts["agent_count"] < 2
                or parts["topology"] not in ("solo", "peer")):
            continue
        if tokens.get(rid, 0.0) <= 0:
            continue
        m = run_metrics(edges)
        if m["n_edges"] < 3 or m.get("duration_s", 0.0) <= 0:
            continue
        draws[parts["topology"]].append((parts, m))

    solo_prof = mean_profile(draws["solo"])
    peer_prof = mean_profile(draws["peer"])

    lines.append(f"### {family_label} — temporal shape, solo draw vs peer draw")
    lines.append("")
    lines.append(f"- solo runs pooled: {len(draws['solo'])}; "
                 f"peer runs pooled: {len(draws['peer'])}")
    lines.append("- max per-decile |solo - peer| of the mean activity profile, "
                 "by edge type (10 deciles):")
    diffs = {}
    peak = 0.0
    for t in EDGE_TYPES:
        sp, pp = solo_prof.get(t, []), peer_prof.get(t, [])
        per_decile = [abs(sp[i] - pp[i]) for i in range(len(sp))
                      if not (math.isnan(sp[i]) or math.isnan(pp[i]))]
        md = max(per_decile) if per_decile else float("nan")
        diffs[t] = md
        peak = max([peak] + [v for v in sp + pp if not math.isnan(v)])
        lines.append(f"    - {t}: {md:.3f}")
    overall = max(v for v in diffs.values() if not math.isnan(v))
    lines.append(f"- max across edge types: **{overall:.3f}** "
                 f"(all {'<' if overall < 0.05 else '>='} 0.05); "
                 f"peak profile value for context: {peak:.3f}")
    lines.append("")
    return diffs, peak


def main():
    f1 = load(F1_CSV)
    f2 = load(F2_CSV)
    lines = []
    lines.append("# Solo-vs-peer reliability + robustness analysis")
    lines.append("")
    lines.append("Generated by `scripts/analyse_solo_peer_reliability.py`. "
                 "At n>=2 solo and peer are the same configuration "
                 "(`memory/experiments/solo-equals-peer-finding.md`); this "
                 "quantifies the accidental same-config/different-session "
                 "replication and the robustness of RQ1/RQ3 to the framing.")
    lines.append("")

    lines.append("## A. Reliability (test-retest across sessions)")
    lines.append("")
    c1 = reliability(f1, "process_orders", lines)
    c2 = reliability(f2, "summarise_transactions", lines)
    tot_cells = c1[0] + c2[0]
    tot_sig = c1[1] + c2[1]
    tot_sig_exact = c1[2] + c2[2]
    lines.append(
        f"**Overall:** under the tie-corrected normal approximation "
        f"{tot_sig}/{tot_cells} matched same-config cells differ significantly "
        f"(F1 {c1[1]}/{c1[0]}, F2 {c2[1]}/{c2[0]}); under the exact permutation "
        f"test {tot_sig_exact}/{tot_cells} (F1 {c1[2]}/{c1[0]}, F2 "
        f"{c2[2]}/{c2[0]}). This is the platform reproducibility ceiling.")
    lines.append("")

    lines.append("## B. RQ1 scaling robustness")
    lines.append("")
    rq1_robustness(f1, "process_orders", lines)
    rq1_robustness(f2, "summarise_transactions", lines)

    lines.append("## C. RQ3 orchestrator-vs-flat robustness")
    lines.append("")
    rq3_robustness(f1, "process_orders", lines)
    rq3_robustness(f2, "summarise_transactions", lines)

    lines.append("## D. Collection-gap timing (§5.5)")
    lines.append("")
    g1 = collection_gaps(F1_TURNS, "process_orders (Family 1)", lines)
    g2 = collection_gaps(F2_TURNS, "summarise_transactions (Family 2)", lines)

    lines.append("## E. Temporal-shape reliability — per-draw decile profiles "
                 "(§5.6)")
    lines.append("")
    d1, peak1 = decile_profile_comparison(
        F1_ROOT, "process_orders", "process_orders (Family 1)", lines)
    d2, peak2 = decile_profile_comparison(
        F2_ROOT, "summarise_transactions",
        "summarise_transactions (Family 2)", lines)

    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"wrote {OUT}")

    # Emit per-cell scatter data for the reliability figure.
    with open(SCATTER_CSV, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=[
            "family", "n", "policy", "pattern",
            "peer_a2a", "solo_a2a", "mw_p", "significant",
            "exact_p", "exact_significant"])
        w.writeheader()
        w.writerows(SCATTER_ROWS)
    print(f"wrote {SCATTER_CSV} ({len(SCATTER_ROWS)} cells)")
    print(f"reliability approx: {tot_sig}/{tot_cells} "
          f"(F1 {c1[1]}/{c1[0]}, F2 {c2[1]}/{c2[0]}); "
          f"exact: {tot_sig_exact}/{tot_cells} "
          f"(F1 {c1[2]}/{c1[0]}, F2 {c2[2]}/{c2[0]})")
    print(f"collection gap median: F1 {g1['gap_median']:.2f} h, "
          f"F2 {g2['gap_median']:.2f} h; within-draw span median F1 "
          f"{g1['within_median']:.2f} h, F2 {g2['within_median']:.2f} h; "
          f"two-block F1={g1['two_block']} F2={g2['two_block']}")
    print(f"temporal-shape max|solo-peer| F1 a2a/a2f/f2a "
          f"{d1['a2a']:.3f}/{d1['a2f']:.3f}/{d1['f2a']:.3f}; "
          f"F2 {d2['a2a']:.3f}/{d2['a2f']:.3f}/{d2['f2a']:.3f}; "
          f"overall max {max(list(d1.values()) + list(d2.values())):.3f} "
          f"(peak profile F1 {peak1:.2f}, F2 {peak2:.2f})")


if __name__ == "__main__":
    main()
