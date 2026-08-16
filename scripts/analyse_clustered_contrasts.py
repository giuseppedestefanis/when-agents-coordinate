#!/usr/bin/env python3
"""Review issues 3 and 4: session-clustered file-count contrasts, and the
per-session n=8 token-reduction range.

Both re-aggregate runs.csv to the draw (cell-by-session) level before testing,
to address the pseudo-replication in the run-level §5.4 contrasts. The
pre-registered run-level tests stay as committed; these clustered values
replace the 1e-26..1e-34 run-level magnitudes in prose.

Issue 3 — clustered policy-axis file-count contrasts (distinct file paths per
run = n_file_nodes). A *draw* is one (topology, pattern) session; there are
3 topologies x 3 patterns = 9 draws per policy per team size. We aggregate each
draw to its mean n_file_nodes and test the policy contrast on the 9 draw-means
(Mann-Whitney and Welch t), plus a linear mixed model with a per-draw random
intercept on the run-level data when statsmodels is available.

Issue 4 — per-session token reduction. At n=8, mean per-run total_output_tokens
under mandatory vs allowed, separately for solo / peer / orchestrator (the
three sessions; 3 patterns pooled, N=30 each), and the % reduction per draw,
against the pooled 42% (Family 1: 167,834 vs 288,735).

Usage:
    .venv/bin/python scripts/analyse_clustered_contrasts.py
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import statistics
import sys
from collections import defaultdict

from scipy import stats as ss

try:
    import warnings
    import pandas as pd
    import statsmodels.formula.api as smf
    # the vs-mandatory draws are near-homogeneous, so the random-effect
    # covariance is often singular; the LMM is reported only as a cross-check.
    warnings.filterwarnings("ignore", module="statsmodels")
    _HAVE_SM = True
except ImportError:
    _HAVE_SM = False

RUN_RE = re.compile(
    r"^family-(?P<fam>\d+)-(?P<task>[a-z_0-9]+)"
    r"-(?P<pattern>clean|overlapping|conflicting)"
    r"-a(?P<n>\d+)-(?P<topo>solo|peer|orchestrator)"
    r"-(?P<pol>forbidden|allowed|mandatory)-r\d+$")

POLICIES = ("forbidden", "allowed", "mandatory")
SHORT = {"forbidden": "forb", "allowed": "allow", "mandatory": "mand"}

FAMILIES = [
    ("Family 1", "process_orders", "data/family-1-full/master/runs.csv"),
    ("Family 2", "summarise_transactions", "data/family-2-full/master/runs.csv"),
]


def load(path, task):
    rows = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            m = RUN_RE.match(r["run_id"])
            if not m or m["task"] != task:
                continue
            rec = {"n": int(m["n"]), "topo": m["topo"], "pol": m["pol"],
                   "patt": m["pattern"]}
            for k, col in (("file", "n_file_nodes"),
                           ("tokens", "total_output_tokens")):
                try:
                    rec[k] = float(r[col])
                except (KeyError, ValueError, TypeError):
                    rec[k] = float("nan")
            rows.append(rec)
    return rows


def _sel(rows, n, pol):
    return [r for r in rows if r["n"] == n and r["pol"] == pol]


def draw_means(rows, n, pol, metric="file"):
    """Mean of `metric` per (topology, pattern) draw at this (n, policy)."""
    by = defaultdict(list)
    for r in _sel(rows, n, pol):
        v = r[metric]
        if v == v:  # not nan
            by[(r["topo"], r["patt"])].append(v)
    return [statistics.fmean(v) for v in by.values() if v]


def run_vals(rows, n, pol, metric="file"):
    return [r[metric] for r in _sel(rows, n, pol) if r[metric] == r[metric]]


def lmm_policy_p(rows, n, pol_a, pol_b):
    """Mixed model n_file_nodes ~ C(policy) with a per-draw random intercept
    (draw = topology|pattern|policy session). Returns the policy fixed-effect
    p, or nan if statsmodels is unavailable / the fit fails."""
    if not _HAVE_SM:
        return float("nan")
    recs = [{"file": r["file"], "pol": r["pol"],
             "draw": f"{r['topo']}|{r['patt']}|{r['pol']}"}
            for r in rows if r["n"] == n and r["pol"] in (pol_a, pol_b)
            and r["file"] == r["file"]]
    if len({rr["pol"] for rr in recs}) < 2:
        return float("nan")
    df = pd.DataFrame(recs)
    try:
        fit = smf.mixedlm("file ~ C(pol)", df, groups=df["draw"]).fit(
            reml=False, method="lbfgs")
        terms = [c for c in fit.pvalues.index if c.startswith("C(pol)")]
        return float(fit.pvalues[terms[0]]) if terms else float("nan")
    except Exception:
        return float("nan")


def _mw(a, b):
    if len(a) < 1 or len(b) < 1:
        return float("nan")
    return float(ss.mannwhitneyu(a, b, alternative="two-sided")[1])


def _welch(a, b):
    if len(a) < 2 or len(b) < 2:
        return float("nan")
    return float(ss.ttest_ind(a, b, equal_var=False)[1])


def issue3(lines):
    lines.append("## Issue 3 — session-clustered file-count contrasts")
    lines.append("")
    lines.append("Draw = (topology, pattern) session; 9 draws per policy per "
                 "team size. Clustered tests are on the 9 draw-means; run-level "
                 "p is shown for reference (the committed pre-registered test).")
    lines.append("")
    lines.append("| family | n | contrast | run-level MW p | draw-MW p | "
                 "draw-Welch p | LMM p | draw means (A vs B) |")
    lines.append("|---|---|---|---|---|---|---|---|")
    plan = {
        "process_orders": [(n, p) for n in (2, 4, 8)
                           for p in (("forbidden", "allowed"),
                                     ("forbidden", "mandatory"),
                                     ("allowed", "mandatory"))],
        "summarise_transactions": (
            [(2, p) for p in (("forbidden", "allowed"),
                              ("forbidden", "mandatory"),
                              ("allowed", "mandatory"))]
            + [(4, ("forbidden", "allowed")), (8, ("forbidden", "allowed"))]),
    }
    for fam_label, task, path in FAMILIES:
        rows = load(path, task)
        for n, (pa, pb) in plan[task]:
            ra, rb = run_vals(rows, n, pa), run_vals(rows, n, pb)
            da, db = draw_means(rows, n, pa), draw_means(rows, n, pb)
            run_p = _mw(ra, rb)
            dmw = _mw(da, db)
            dwt = _welch(da, db)
            lmm = lmm_policy_p(rows, n, pa, pb)
            lines.append(
                f"| {fam_label} | {n} | {SHORT[pa]}-{SHORT[pb]} | "
                f"{run_p:.2e} | {dmw:.4f} | {dwt:.4f} | "
                f"{('%.4f' % lmm) if lmm == lmm else 'n/a'} | "
                f"{statistics.fmean(da):.2f} vs {statistics.fmean(db):.2f} "
                f"(n={len(da)}/{len(db)} draws) |")
    lines.append("")


def issue4(lines):
    lines.append("## Issue 4 — per-session n=8 token reduction "
                 "(mandatory vs allowed)")
    lines.append("")
    lines.append("Family 1, n=8, mean per-run total_output_tokens; 3 patterns "
                 "pooled per draw (N=30). % reduction = (allowed - mandatory) "
                 "/ allowed.")
    lines.append("")
    lines.append("| draw (topology) | mandatory mean | allowed mean | "
                 "% reduction | N mand / allow |")
    lines.append("|---|---|---|---|---|")
    rows = load("data/family-1-full/master/runs.csv", "process_orders")
    reductions = []
    for topo in ("solo", "peer", "orchestrator"):
        m = [r["tokens"] for r in rows if r["n"] == 8 and r["topo"] == topo
             and r["pol"] == "mandatory" and r["tokens"] == r["tokens"]]
        a = [r["tokens"] for r in rows if r["n"] == 8 and r["topo"] == topo
             and r["pol"] == "allowed" and r["tokens"] == r["tokens"]]
        mm, am = statistics.fmean(m), statistics.fmean(a)
        red = (am - mm) / am * 100
        reductions.append(red)
        lines.append(f"| {topo} | {mm:,.0f} | {am:,.0f} | {red:.1f}% | "
                     f"{len(m)}/{len(a)} |")
    # pooled
    mp = [r["tokens"] for r in rows if r["n"] == 8 and r["pol"] == "mandatory"
          and r["tokens"] == r["tokens"]]
    ap = [r["tokens"] for r in rows if r["n"] == 8 and r["pol"] == "allowed"
          and r["tokens"] == r["tokens"]]
    pooled = (statistics.fmean(ap) - statistics.fmean(mp)) / \
        statistics.fmean(ap) * 100
    lines.append(f"| **pooled** | {statistics.fmean(mp):,.0f} | "
                 f"{statistics.fmean(ap):,.0f} | {pooled:.1f}% | "
                 f"{len(mp)}/{len(ap)} |")
    lines.append("")
    lines.append(f"Per-draw reduction range: "
                 f"{min(reductions):.1f}% - {max(reductions):.1f}% "
                 f"(pooled {pooled:.1f}%).")
    lines.append("")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="memory/experiments/"
                    "review-issues-3-4-clustered.md")
    args = ap.parse_args()
    lines = ["# Review issues 3 & 4: clustered contrasts + token range", ""]
    lines.append("Generated by `scripts/analyse_clustered_contrasts.py`.")
    lines.append("")
    issue3(lines)
    issue4(lines)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"wrote {args.out}")
    if not _HAVE_SM:
        print("(statsmodels not available; LMM column is n/a)")


if __name__ == "__main__":
    main()
