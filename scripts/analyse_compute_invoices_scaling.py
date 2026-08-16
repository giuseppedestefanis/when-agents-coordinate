#!/usr/bin/env python3
"""H7 compute_invoices scaling arm — analysis script.

Reads:
  data/compute-invoices-scaling/master/runs.csv  — 30 fresh H7 runs
  data/family-2-full/master/runs.csv             — old n=4 batch (stability
                                                    check only, NOT in H7 fit)

Produces:
  memory/experiments/compute-invoices-scaling/results.md

Statistical tests:
  1. Per-cell summary: N, successes, success rate (Wilson 95% CI), a2a
     mean and SD at n=2, n=4, n=8.
  2. Overall log-log regression: slope of log(a2a) on log(n) over all 30
     per-run observations, with 95% CI via t-distribution (df = N-2).
  3. Piecewise log-log regression with knot fixed at n=4:
       model: log(a2a) = β₀ + β₁·log(n) + β₂·(log(n)−log(4))₊ + ε
     where (·)₊ = max(0,·).  Then:
       β(2→4) = β₁            (slope on the left segment)
       β(4→8) = β₁ + β₂       (slope on the right segment)
       Δ = β(2→4) − β(4→8) = −β₂
     Fit by OLS over all 30 runs; 95% CIs from t-distribution (df = N−3).
  4. Mann-Whitney stability check: old n=4 batch (family-2-full) vs new
     n=4 batch (compute-invoices-scaling). Two-sided, on n_agent_to_agent.
     This is a free cross-batch check — old runs are excluded from the fit.

Decision rule (from memory/experiments/compute-invoices-scaling/design.md):
  (a) Δ CI excludes 0, Δ > 0  → confirmed (break at n=4 despite 8 units)
  (b) β(4→8) CI contains 2.0 AND Δ CI centred near 0
                               → refuted (no deceleration at n=4)
  (c) Neither                  → directional; report Δ against reference
                                 range [1.32, 1.70] from existing families.

Reference values (from pre-registered design, 2026-06-09):
  F1 n=4→8 slope: 1.32
  F2 n=4→8 slope: 1.70
  n² prediction:  2.00
  F1 Δ:           0.90   (detectable at N=10/cell)
  F2 Δ:           0.44   (likely not detectable at N=10/cell)

Usage:

    .venv/bin/python scripts/analyse_compute_invoices_scaling.py
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Reference values from pre-registered design
# ---------------------------------------------------------------------------

F1_SLOPE_4TO8 = 1.32
F2_SLOPE_4TO8 = 1.70
N2_PREDICTION = 2.00
F1_DELTA = 0.90
F2_DELTA = 0.44

AGENT_COUNTS = (2, 4, 8)
N_CELLS = 3
N_PER_CELL = 10
N_TOTAL = 30


# ---------------------------------------------------------------------------
# Utility: Wilson CI, OLS, piecewise regression, t-critical
# ---------------------------------------------------------------------------

def wilson_ci(k, n, z=1.96):
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def t_critical_95(df):
    """Approximate two-sided 95% t critical value via Wilson–Hilferty cube-root
    normal approximation.  Accurate to <0.001 for df >= 5."""
    if df <= 0:
        return float("inf")
    if df >= 1000:
        return 1.96
    # Coefficients from Abramowitz & Stegun 26.7.8 approximation
    a = 0.147
    x = 0.95  # two-sided: use 0.975 quantile of standard normal
    # Use rational approximation for Φ^{-1}(0.975)
    # More precisely: use the classical series via the incomplete beta function
    # approximation for small df.  For the range df in [5, 120] relevant here,
    # use the Cornish-Fisher expansion:
    #   t_{p,df} ≈ z + g₁/df + g₂/df² + ...
    # where z = Φ^{-1}(0.975) = 1.959964...
    z = 1.959964
    g1 = (z**3 + z) / 4
    g2 = (5 * z**5 + 16 * z**3 + 3 * z) / 96
    g3 = (3 * z**7 + 19 * z**5 + 17 * z**3 - 15 * z) / 384
    g4 = (79 * z**9 + 776 * z**7 + 1482 * z**5 - 1920 * z**3 - 945 * z) / 92160
    t = z + g1 / df + g2 / df**2 + g3 / df**3 + g4 / df**4
    return t


def ols_simple(xs, ys):
    """Simple OLS: y = b0 + b1*x.  Returns (b0, b1, se_b1, r2)."""
    n = len(xs)
    if n < 2:
        return (float("nan"),) * 4
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    if sxx == 0:
        return (float("nan"),) * 4
    b1 = sxy / sxx
    b0 = my - b1 * mx
    y_hat = [b0 + b1 * x for x in xs]
    sse = sum((y - yh) ** 2 for y, yh in zip(ys, y_hat))
    sst = sum((y - my) ** 2 for y in ys)
    r2 = 1.0 - sse / sst if sst > 0 else float("nan")
    s2 = sse / (n - 2)
    se_b1 = math.sqrt(s2 / sxx) if s2 >= 0 else float("nan")
    return (b0, b1, se_b1, r2)


def ols_piecewise(log_ns, log_a2as, knot=math.log(4)):
    """Piecewise OLS with fixed knot at log(4).

    Model: y = β₀ + β₁·x + β₂·(x - knot)₊
    Returns (b1, b2, se_b1, se_b2, cov_b1_b2, sse, df_resid).
    β(2→4) = b1, β(4→8) = b1+b2, Δ = -b2.
    """
    n = len(log_ns)
    if n < 3:
        nans = (float("nan"),) * 7
        return nans

    # Build design matrix X (n×3): [1, x, max(0, x-knot)]
    X = []
    for x in log_ns:
        hinge = max(0.0, x - knot)
        X.append((1.0, x, hinge))

    # Solve via normal equations X'X β = X'y
    # X'X is 3×3
    xtx = [[0.0] * 3 for _ in range(3)]
    xty = [0.0] * 3
    for i in range(n):
        for r in range(3):
            xty[r] += X[i][r] * log_a2as[i]
            for c in range(3):
                xtx[r][c] += X[i][r] * X[i][c]

    # Invert 3×3 matrix
    def inv3(m):
        a, b, c = m[0]
        d, e, f = m[1]
        g, h, k = m[2]
        det = (a * (e * k - f * h)
               - b * (d * k - f * g)
               + c * (d * h - e * g))
        if abs(det) < 1e-15:
            return None
        inv = [
            [(e * k - f * h) / det, (c * h - b * k) / det,
             (b * f - c * e) / det],
            [(f * g - d * k) / det, (a * k - c * g) / det,
             (c * d - a * f) / det],
            [(d * h - e * g) / det, (b * g - a * h) / det,
             (a * e - b * d) / det],
        ]
        return inv

    xtx_inv = inv3(xtx)
    if xtx_inv is None:
        nans = (float("nan"),) * 7
        return nans

    # β = (X'X)^{-1} X'y
    beta = [sum(xtx_inv[r][c] * xty[c] for c in range(3)) for r in range(3)]
    b0, b1, b2 = beta

    # Residuals and SSE
    y_hat = [b0 + b1 * x + b2 * max(0.0, x - knot) for x in log_ns]
    sse = sum((y - yh) ** 2 for y, yh in zip(log_a2as, y_hat))
    df_resid = n - 3

    if df_resid <= 0:
        nans = (float("nan"),) * 7
        return nans

    s2 = sse / df_resid
    # SEs from diagonal of (X'X)^{-1} * s²
    se_b1 = math.sqrt(s2 * xtx_inv[1][1]) if s2 * xtx_inv[1][1] >= 0 else float("nan")
    se_b2 = math.sqrt(s2 * xtx_inv[2][2]) if s2 * xtx_inv[2][2] >= 0 else float("nan")
    cov_b1_b2 = s2 * xtx_inv[1][2]

    return (b1, b2, se_b1, se_b2, cov_b1_b2, sse, df_resid)


def mannwhitneyu(xs, ys, alternative="two-sided"):
    """Pure-Python Mann-Whitney U with normal approximation (two-sided).
    Uses tie correction. Returns (U, p).
    """
    nx, ny = len(xs), len(ys)
    if nx == 0 or ny == 0:
        return (float("nan"), float("nan"))

    # Rank all observations together
    combined = sorted([(v, 0) for v in xs] + [(v, 1) for v in ys])
    # Assign mid-ranks for ties
    ranks = [0.0] * (nx + ny)
    i = 0
    while i < len(combined):
        j = i
        while j < len(combined) and combined[j][0] == combined[i][0]:
            j += 1
        mid_rank = (i + j + 1) / 2.0  # 1-indexed mid-rank
        for k in range(i, j):
            ranks[k] = mid_rank
        i = j

    # Tie correction factor
    i = 0
    tie_sum = 0.0
    while i < len(combined):
        j = i
        while j < len(combined) and combined[j][0] == combined[i][0]:
            j += 1
        t = j - i
        if t > 1:
            tie_sum += t ** 3 - t
        i = j

    # U statistics
    rx = sum(ranks[k] for k in range(len(combined)) if combined[k][1] == 0)
    ry = sum(ranks[k] for k in range(len(combined)) if combined[k][1] == 1)
    ux = rx - nx * (nx + 1) / 2
    uy = ry - ny * (ny + 1) / 2
    u = min(ux, uy)

    # Normal approximation with tie correction
    n_total = nx + ny
    mean_u = nx * ny / 2
    var_u = (nx * ny / (n_total * (n_total - 1))) * (
        (n_total ** 3 - n_total) / 12 - tie_sum / 12)
    if var_u <= 0:
        return (u, float("nan"))
    z = (u - mean_u) / math.sqrt(var_u)

    # Two-tailed p via standard normal CDF approximation
    def norm_cdf(z):
        # Abramowitz & Stegun 26.2.17
        t = 1.0 / (1.0 + 0.2316419 * abs(z))
        poly = t * (0.319381530
                    + t * (-0.356563782
                           + t * (1.781477937
                                  + t * (-1.821255978
                                         + t * 1.330274429))))
        p_upper = poly * math.exp(-0.5 * z * z) / math.sqrt(2 * math.pi)
        return p_upper if z < 0 else 1.0 - p_upper

    p_one = norm_cdf(-abs(z))
    return (u, 2 * p_one)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_ok_run_ids(ledger_path):
    if not os.path.exists(ledger_path):
        return None   # None = accept all (no ledger filter)
    try:
        with open(ledger_path) as f:
            ledger = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(ledger, dict):
        rows = (ledger["runs"] if isinstance(ledger.get("runs"), list)
                else list(ledger.values()))
    else:
        rows = ledger
    return {r["run_id"] for r in rows if r.get("status") == "ok" and r.get("run_id")}


def load_runs_csv(path, ok_run_ids=None, task_filter=None, n_filter=None):
    """Load runs.csv rows, optionally filtered by task and/or agent count.
    Returns list of dicts with numeric fields cast.
    """
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            if ok_run_ids is not None and row["run_id"] not in ok_run_ids:
                continue
            try:
                n = int(row["agent_count"])
            except (KeyError, ValueError):
                continue
            if n_filter is not None and n not in n_filter:
                continue
            # instance field encodes "task_id/pattern" in family-2
            inst = row.get("instance", "")
            task_id = inst.split("/")[0] if "/" in inst else inst
            if task_filter is not None and task_id != task_filter:
                continue
            row["agent_count_int"] = n
            row["task_id"] = task_id
            row["success_b"] = row.get("success", "").lower() == "true"
            for k in ("n_agent_to_agent", "n_agent_to_agent_directed",
                      "n_agent_to_file", "n_file_to_agent",
                      "n_file_nodes", "completion_time_s"):
                try:
                    row[k] = float(row[k])
                except (KeyError, ValueError, TypeError):
                    row[k] = float("nan")
            rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Decision rule
# ---------------------------------------------------------------------------

def apply_decision_rule(beta_low, beta_high, delta_low, delta_high,
                        delta_est, beta4to8_est):
    """Apply the H7 pre-registered decision rule.

    Returns (verdict, explanation) where verdict ∈ {'confirmed','refuted','directional'}.
    """
    # (a) Δ CI excludes 0 from below, Δ > 0
    if delta_low > 0:
        return (
            "confirmed",
            f"Δ = {delta_est:.2f} (95% CI [{delta_low:.2f}, {delta_high:.2f}]) "
            f"excludes 0 from below. Break at n=4 appears in compute_invoices "
            f"despite 8 task units — coordination property interpretation "
            f"supported."
        )
    # (b) β(4→8) CI contains 2.0 AND Δ CI centred near 0
    if beta_low <= N2_PREDICTION <= beta_high and abs(delta_est) < 0.3:
        return (
            "refuted",
            f"β(4→8) = {beta4to8_est:.2f} CI [{beta_low:.2f}, {beta_high:.2f}] "
            f"contains n²=2.0 and Δ ≈ 0. No deceleration at n=4; unit-count "
            f"tracking interpretation supported."
        )
    # (c) Neither
    return (
        "directional",
        f"Δ = {delta_est:.2f} (95% CI [{delta_low:.2f}, {delta_high:.2f}]). "
        f"Does not satisfy (a) or (b). Report Δ against reference range "
        f"[{F1_DELTA:.2f} (F1), {F2_DELTA:.2f} (F2)]; "
        f"N=10/cell insufficient to distinguish at F2 magnitude."
    )


# ---------------------------------------------------------------------------
# Report renderer
# ---------------------------------------------------------------------------

def render_report(
        new_rows, old_n4_rows, cell_stats,
        overall_slope, overall_se, overall_r2, overall_n, overall_df,
        b1, b2, se_b1, se_b2, cov_b1_b2,
        t_crit,
        mw_u, mw_p,
        verdict, verdict_explanation,
        out_path):

    beta_2to4 = b1
    beta_4to8 = b1 + b2
    delta_est = -b2
    se_delta = se_b2  # Δ = -β₂, so SE(Δ) = SE(β₂)

    # 95% CIs
    overall_ci_low = overall_slope - t_crit * overall_se
    overall_ci_high = overall_slope + t_crit * overall_se

    ci_b1_low = b1 - t_crit * se_b1
    ci_b1_high = b1 + t_crit * se_b1

    # SE(β(4→8)) = SE(β₁ + β₂) = sqrt(Var(β₁) + Var(β₂) + 2·Cov(β₁,β₂))
    var_b4to8 = se_b1**2 + se_b2**2 + 2 * cov_b1_b2
    se_b4to8 = math.sqrt(var_b4to8) if var_b4to8 >= 0 else float("nan")
    ci_b4to8_low = beta_4to8 - t_crit * se_b4to8
    ci_b4to8_high = beta_4to8 + t_crit * se_b4to8

    ci_delta_low = delta_est - t_crit * se_delta
    ci_delta_high = delta_est + t_crit * se_delta

    lines = []
    lines.append("# H7 compute_invoices scaling arm — results")
    lines.append("")
    lines.append("Generated by `scripts/analyse_compute_invoices_scaling.py`.")
    lines.append("Pre-registered design: "
                 "`memory/experiments/compute-invoices-scaling/design.md`.")
    lines.append("Pre-commitment commit: `dfad8a0`.")
    lines.append("")

    # --- batch state ---
    n_new = len(new_rows)
    n_ok = n_new
    n_succ = sum(1 for r in new_rows if r["success_b"])
    lines.append("## Batch state")
    lines.append("")
    lines.append(f"- New H7 runs loaded: {n_new} of {N_TOTAL} expected")
    lines.append(f"- Verifier successes: {n_succ} / {n_ok}")
    if old_n4_rows:
        lines.append(f"- Old n=4 runs (stability check only): {len(old_n4_rows)}")
    lines.append("")

    # --- per-cell summary ---
    lines.append("## Per-cell summary (new H7 batch only)")
    lines.append("")
    lines.append("| n | N | succ | success rate (95% CI) | "
                 "a2a mean (SD) | a2f mean (SD) | wall mean (SD) |")
    lines.append("|---|---:|---:|---|---|---|---|")
    for n in AGENT_COUNTS:
        if n not in cell_stats:
            lines.append(f"| {n} | 0 | — | — | — | — | — |")
            continue
        s = cell_stats[n]
        ci_lo, ci_hi = wilson_ci(s["successes"], s["n"])
        sr = f"{s['success_rate']:.2f} ({ci_lo:.2f}–{ci_hi:.2f})"
        a2a = f"{s['a2a_mean']:.1f} ({s['a2a_sd']:.1f})"
        a2f = f"{s['a2f_mean']:.1f} ({s['a2f_sd']:.1f})"
        wall = f"{s['wall_mean']:.0f}s ({s['wall_sd']:.0f})"
        lines.append(
            f"| {n} | {s['n']} | {s['successes']} | {sr} | "
            f"{a2a} | {a2f} | {wall} |")
    lines.append("")

    # --- overall log-log regression ---
    lines.append("## Overall log-log regression (all 30 runs, single slope)")
    lines.append("")
    lines.append(f"Slope β = {overall_slope:.3f} "
                 f"(95% CI [{overall_ci_low:.3f}, {overall_ci_high:.3f}]; "
                 f"SE = {overall_se:.3f}; R² = {overall_r2:.3f}; "
                 f"df = {overall_df})")
    lines.append(f"Reference: n² = 2.00; F1 full slope ≈ 1.61 (pilot 1.63); "
                 f"F2 full slope ≈ 1.70.")
    lines.append("")

    # --- piecewise regression ---
    lines.append("## Piecewise log-log regression (knot at n=4)")
    lines.append("")
    lines.append("Model: log(a2a) = β₀ + β₁·log(n) + β₂·(log(n)−log(4))₊")
    lines.append("")
    lines.append(f"| parameter | estimate | 95% CI | SE |")
    lines.append("|---|---|---|---|")
    lines.append(f"| β(2→4) = β₁ | {beta_2to4:.3f} | "
                 f"[{ci_b1_low:.3f}, {ci_b1_high:.3f}] | {se_b1:.3f} |")
    lines.append(f"| β(4→8) = β₁+β₂ | {beta_4to8:.3f} | "
                 f"[{ci_b4to8_low:.3f}, {ci_b4to8_high:.3f}] | {se_b4to8:.3f} |")
    lines.append(f"| Δ = β(2→4)−β(4→8) = −β₂ | {delta_est:.3f} | "
                 f"[{ci_delta_low:.3f}, {ci_delta_high:.3f}] | {se_delta:.3f} |")
    lines.append("")
    lines.append("Reference ranges:")
    lines.append(f"  F1 Δ = {F1_DELTA:.2f} (detectable at N=10/cell); "
                 f"F2 Δ = {F2_DELTA:.2f} (likely not detectable at N=10/cell).")
    lines.append(f"  F1 β(4→8) = {F1_SLOPE_4TO8:.2f}; "
                 f"F2 β(4→8) = {F2_SLOPE_4TO8:.2f}; n² = {N2_PREDICTION:.2f}.")
    lines.append("")

    # --- two-point segment ratios ---
    n2_mean = cell_stats.get(2, {}).get("a2a_mean", float("nan"))
    n4_mean = cell_stats.get(4, {}).get("a2a_mean", float("nan"))
    n8_mean = cell_stats.get(8, {}).get("a2a_mean", float("nan"))
    lines.append("## Cell-mean ratios (two-point descriptors)")
    lines.append("")
    if not math.isnan(n2_mean) and n2_mean > 0 and not math.isnan(n4_mean):
        ratio_24 = n4_mean / n2_mean
        lines.append(f"n=2→4 mean ratio: {ratio_24:.2f}  "
                     f"(cell means {n2_mean:.1f} → {n4_mean:.1f})")
    if not math.isnan(n4_mean) and n4_mean > 0 and not math.isnan(n8_mean):
        ratio_48 = n8_mean / n4_mean
        lines.append(f"n=4→8 mean ratio: {ratio_48:.2f}  "
                     f"(cell means {n4_mean:.1f} → {n8_mean:.1f})")
    lines.append("")

    # --- Mann-Whitney stability check ---
    lines.append("## Cross-batch stability check (old n=4 vs new n=4)")
    lines.append("")
    if old_n4_rows:
        n_old = len(old_n4_rows)
        old_a2a = [r["n_agent_to_agent"] for r in old_n4_rows
                   if not math.isnan(r["n_agent_to_agent"])]
        new_a2a = [r["n_agent_to_agent"]
                   for r in new_rows
                   if r["agent_count_int"] == 4
                   and not math.isnan(r["n_agent_to_agent"])]
        old_mean = sum(old_a2a) / len(old_a2a) if old_a2a else float("nan")
        new_mean = sum(new_a2a) / len(new_a2a) if new_a2a else float("nan")
        lines.append(f"Old n=4 (family-2-full): N={n_old}, "
                     f"a2a mean = {old_mean:.1f}")
        lines.append(f"New n=4 (compute-invoices-scaling): N={len(new_a2a)}, "
                     f"a2a mean = {new_mean:.1f}")
        if not math.isnan(mw_u) and not math.isnan(mw_p):
            lines.append(f"Mann-Whitney U = {mw_u:.0f}, p = {mw_p:.3f} "
                         f"(two-sided, normal approximation)")
            if mw_p > 0.05:
                lines.append("→ no significant difference; batch consistency "
                             "supported.")
            else:
                lines.append(f"→ significant difference (p = {mw_p:.3f}); "
                             f"note: pilot-vs-full shift was also significant "
                             f"(F1 n=8: p=0.034). Interpret with caution.")
    else:
        lines.append("Old n=4 runs not found in data/family-2-full/master/runs.csv. "
                     "Stability check skipped.")
    lines.append("")

    # --- decision rule ---
    lines.append("## H7 decision rule")
    lines.append("")
    lines.append(f"**Verdict: {verdict.upper()}**")
    lines.append("")
    lines.append(verdict_explanation)
    lines.append("")
    lines.append("Decision rule pre-committed 2026-06-09:")
    lines.append("  (a) Δ CI excludes 0 positive → confirmed (break at n=4 "
                 "despite 8 task units)")
    lines.append("  (b) β(4→8) CI contains 2.0 AND Δ CI centred near 0 → "
                 "refuted (no deceleration at n=4)")
    lines.append("  (c) Neither → directional; report Δ against [F1=1.32, "
                 "F2=1.70]; power caveat applies")
    lines.append("")

    # --- notes ---
    lines.append("## Notes")
    lines.append("")
    lines.append("- H7 batch does NOT include the 10 old n=4 runs from "
                 "data/family-2-full/ in the regression; those are stability "
                 "check only (see design rationale re: batch-mixing "
                 "contamination).")
    lines.append("- Piecewise OLS solved via normal equations (pure Python, "
                 "no scipy dependency). CIs from t-distribution with "
                 f"df = N−3 = {N_TOTAL - 3}.")
    lines.append("- Mann-Whitney uses normal approximation with tie correction.")
    lines.append("- Runs with a2a = 0 are excluded from log-log regressions "
                 "(log(0) undefined).")
    lines.append("- Power caveat: at N=10/cell, Δ ≈ F1 magnitude (0.90) is "
                 "detectable; Δ ≈ F2 magnitude (0.44) likely is not. Middle "
                 "result pre-committed to (c).")

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="H7 compute_invoices scaling arm analysis.")
    parser.add_argument(
        "--h7-root", default="data/compute-invoices-scaling",
        help="directory containing the 30 H7 runs")
    parser.add_argument(
        "--f2-full-root", default="data/family-2-full",
        help="directory containing the Family 2 full schedule "
             "(used only for the old n=4 stability check)")
    parser.add_argument(
        "--output",
        default="memory/experiments/compute-invoices-scaling/results.md")
    args = parser.parse_args()

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    h7_runs_csv = os.path.join(repo_root, args.h7_root, "master", "runs.csv")
    h7_ledger = os.path.join(repo_root, args.h7_root, "ledger.json")
    f2_runs_csv = os.path.join(repo_root, args.f2_full_root, "master", "runs.csv")
    f2_ledger = os.path.join(repo_root, args.f2_full_root, "ledger.json")
    out_path = os.path.join(repo_root, args.output)

    # --- load H7 data ---
    h7_ok = load_ok_run_ids(h7_ledger)
    new_rows = load_runs_csv(h7_runs_csv, ok_run_ids=h7_ok,
                              task_filter="compute_invoices")
    if not new_rows:
        print(f"No H7 runs found at {h7_runs_csv}. Has the batch finished?")
        sys.exit(0)
    print(f"Loaded {len(new_rows)} H7 runs from {h7_runs_csv}")

    # --- load old n=4 for stability check ---
    f2_ok = load_ok_run_ids(f2_ledger)
    old_n4_rows = load_runs_csv(f2_runs_csv, ok_run_ids=f2_ok,
                                 task_filter="compute_invoices",
                                 n_filter={4})
    print(f"Loaded {len(old_n4_rows)} old n=4 runs for stability check")

    # --- per-cell stats ---
    by_n = defaultdict(list)
    for r in new_rows:
        by_n[r["agent_count_int"]].append(r)

    cell_stats = {}
    for n in AGENT_COUNTS:
        rs = by_n[n]
        if not rs:
            continue
        a2a_vals = [r["n_agent_to_agent"] for r in rs
                    if not math.isnan(r["n_agent_to_agent"])]
        a2f_vals = [r["n_agent_to_file"] for r in rs
                    if not math.isnan(r["n_agent_to_file"])]
        wall_vals = [r["completion_time_s"] for r in rs
                     if not math.isnan(r["completion_time_s"])]
        def _mean(v): return sum(v) / len(v) if v else float("nan")
        def _sd(v):
            if len(v) < 2: return float("nan")
            m = _mean(v)
            return math.sqrt(sum((x - m)**2 for x in v) / (len(v) - 1))
        cell_stats[n] = {
            "n": len(rs),
            "successes": sum(1 for r in rs if r["success_b"]),
            "success_rate": sum(1 for r in rs if r["success_b"]) / len(rs),
            "a2a_mean": _mean(a2a_vals),
            "a2a_sd": _sd(a2a_vals),
            "a2f_mean": _mean(a2f_vals),
            "a2f_sd": _sd(a2f_vals),
            "wall_mean": _mean(wall_vals),
            "wall_sd": _sd(wall_vals),
        }

    # --- overall log-log regression ---
    log_pairs = [
        (math.log(r["agent_count_int"]), math.log(r["n_agent_to_agent"]))
        for r in new_rows
        if r["n_agent_to_agent"] > 0
    ]
    if len(log_pairs) < 2:
        print("WARNING: fewer than 2 usable (n, a2a) pairs for regression.")
        overall_b0 = overall_b1 = overall_se = overall_r2 = float("nan")
        overall_n = len(log_pairs)
        overall_df = 0
    else:
        xs, ys = zip(*log_pairs)
        overall_b0, overall_b1, overall_se, overall_r2 = ols_simple(
            list(xs), list(ys))
        overall_n = len(log_pairs)
        overall_df = overall_n - 2

    # --- piecewise regression ---
    if len(log_pairs) >= 3:
        log_ns, log_a2as = zip(*log_pairs)
        b1, b2, se_b1, se_b2, cov_b1_b2, sse, df_resid = ols_piecewise(
            list(log_ns), list(log_a2as))
    else:
        b1 = b2 = se_b1 = se_b2 = cov_b1_b2 = float("nan")
        df_resid = 0

    t_crit = t_critical_95(df_resid if df_resid > 0 else 1)

    # --- Mann-Whitney ---
    old_a2a = [r["n_agent_to_agent"] for r in old_n4_rows
               if not math.isnan(r["n_agent_to_agent"])]
    new_n4 = [r["n_agent_to_agent"] for r in new_rows
              if r["agent_count_int"] == 4
              and not math.isnan(r["n_agent_to_agent"])]
    if old_a2a and new_n4:
        mw_u, mw_p = mannwhitneyu(old_a2a, new_n4)
    else:
        mw_u = mw_p = float("nan")

    # --- decision rule ---
    if not math.isnan(b2):
        delta_est = -b2
        se_delta = se_b2
        delta_low = delta_est - t_crit * se_delta
        delta_high = delta_est + t_crit * se_delta
        beta_4to8_est = b1 + b2
        var_b4to8 = se_b1**2 + se_b2**2 + 2 * cov_b1_b2
        se_b4to8 = math.sqrt(var_b4to8) if var_b4to8 >= 0 else float("nan")
        beta_low = beta_4to8_est - t_crit * se_b4to8
        beta_high = beta_4to8_est + t_crit * se_b4to8
        verdict, verdict_explanation = apply_decision_rule(
            beta_low, beta_high, delta_low, delta_high,
            delta_est, beta_4to8_est)
    else:
        verdict = "pending"
        verdict_explanation = "Regression failed (insufficient data)."

    # --- print summary ---
    print()
    print(f"Per-cell a2a means: ", end="")
    for n in AGENT_COUNTS:
        s = cell_stats.get(n)
        if s:
            print(f"n={n}: {s['a2a_mean']:.1f}", end="  ")
    print()
    print(f"Overall log-log slope: {overall_b1:.3f} "
          f"(SE {overall_se:.3f}, R²={overall_r2:.3f})")
    if not math.isnan(b1):
        print(f"β(2→4) = {b1:.3f}, β(4→8) = {b1+b2:.3f}, "
              f"Δ = {-b2:.3f}")
    if not math.isnan(mw_u):
        print(f"Mann-Whitney (old vs new n=4): U={mw_u:.0f}, p={mw_p:.3f}")
    print(f"Verdict: {verdict.upper()}")

    render_report(
        new_rows, old_n4_rows, cell_stats,
        overall_b1, overall_se, overall_r2, overall_n, overall_df,
        b1, b2, se_b1, se_b2, cov_b1_b2,
        t_crit,
        mw_u, mw_p,
        verdict, verdict_explanation,
        out_path,
    )
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
