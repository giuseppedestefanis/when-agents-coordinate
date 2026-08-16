#!/usr/bin/env python3
"""Recompute the method-specific statistics that `verify_claims.py` defers on.

`verify_claims.py` checks 76 headline numbers and then prints one NOTE line:

    H6 p=0.23; centralisation 0.14/0.24 p=0.018; disparity filter;
    exploratory R^2~0.1 -- verified against the repository analysis reports,
    not recomputed here

Those four were computed ad hoc during the study and never scripted, so nobody
could reproduce them from the released package. This script closes that gap.
It reads only `data/*/master/*.csv`, writes nothing outside `data/derived/`,
and prints PASS or FAIL against the value the paper states.

Run:  python3 scripts/verify_method_statistics.py
Needs: pandas, numpy, networkx, scipy
"""
from __future__ import annotations

import math
import os
import sys
from collections import Counter

import networkx as nx
import numpy as np
import pandas as pd
from scipy import stats

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = lambda exp, f: os.path.join(ROOT, "data", exp, "master", f)

_results = []


def check(name, computed, expected, note=""):
    ok = str(computed) == str(expected)
    _results.append(ok)
    tag = "PASS" if ok else "FAIL"
    print(f"{tag:4}  {name:58} computed={computed}  paper={expected}")
    if note:
        print(f"      {note}")
    return ok


def report(name, computed, note=""):
    """Print a quantity the paper describes qualitatively."""
    print(f"INFO  {name:58} computed={computed}")
    if note:
        print(f"      {note}")


# ---------------------------------------------------------------- helpers ---
def point_to_point(edges: pd.DataFrame) -> pd.DataFrame:
    """Agent-to-agent messages aimed at a real teammate, self-loops removed."""
    m = edges[(edges.edge_type == "agent_to_agent")
              & (edges.target_kind.isin(["canonical", "alias"]))]
    return m[m.source != m.target]


def freeman_centralisation(graph) -> float:
    """Freeman degree centralisation: 0 for a flat graph, 1 for a star."""
    n = graph.number_of_nodes()
    if n < 3:
        return math.nan
    ci = {v: d / (n - 1) for v, d in dict(graph.degree()).items()}
    cmax = max(ci.values())
    return sum(cmax - c for c in ci.values()) / (n - 2)


def per_run_centralisation(edges: pd.DataFrame) -> dict:
    out = {}
    for run_id, g in point_to_point(edges).groupby("run_id"):
        dg = nx.DiGraph()
        dg.add_edges_from(zip(g.source, g.target))
        out[run_id] = freeman_centralisation(dg.to_undirected())
    return out


def disparity_backbone(pairs: Counter, alpha: float) -> set:
    """Edges surviving the disparity filter of Serrano et al. (2009).

    An edge (u, v) with weight w survives if it is significant against the
    null that u's (or v's) weights are distributed uniformly at random over
    its k incident edges: (1 - w/s)^(k-1) < alpha.
    """
    out_s, out_k = Counter(), Counter()
    in_s, in_k = Counter(), Counter()
    for (u, v), w in pairs.items():
        out_s[u] += w; out_k[u] += 1
        in_s[v] += w; in_k[v] += 1
    keep = set()
    for (u, v), w in pairs.items():
        ku, kv = out_k[u], in_k[v]
        if ku > 1 and (1 - w / out_s[u]) ** (ku - 1) < alpha:
            keep.add((u, v))
        elif kv > 1 and (1 - w / in_s[v]) ** (kv - 1) < alpha:
            keep.add((u, v))
    return keep


# ------------------------------------------------------------------ checks ---
def centralisation_contrast(e1: pd.DataFrame, r1: pd.DataFrame) -> None:
    print("\n== Centralisation (Finding 3, structural leg) ====================")
    r1 = r1.copy()
    r1["centr"] = r1.run_id.map(per_run_centralisation(e1))
    d = r1[(r1.agent_count == 8) & r1.centr.notna()]

    peer = d[d.topology == "peer"].centr
    orch = d[d.topology == "orchestrator"].centr
    u, p = stats.mannwhitneyu(peer, orch)
    check("centralisation, collection B vs orchestrator (medians)",
          f"{peer.median():.2f} vs {orch.median():.2f}", "0.24 vs 0.14")
    check("centralisation, collection B vs orchestrator (U, p)",
          f"U={u:.0f}, p={p:.3f}", "U=4265, p=0.018")

    flat = d[d.topology.isin(["solo", "peer"])].centr
    uf, pf = stats.mannwhitneyu(flat, orch)
    report("SAME CONTRAST with both flat collections pooled",
           f"{flat.median():.3f} vs {orch.median():.3f}, p={pf:.3f}",
           "The paper words this contrast as 'the flat ones'. Pooled, the "
           "difference disappears; the published figure is collection B only.")

    lo, hi = orch.min(), orch.max()
    report("orchestrator absolute centralisation, range over runs",
           f"{lo:.2f} to {hi:.2f}",
           "The no-hub reading rests on this absolute level, which holds "
           "under every variant, rather than on the contrast above.")


def disparity_filter_backbone(e1: pd.DataFrame, r1: pd.DataFrame,
                              e2: pd.DataFrame, r2: pd.DataFrame) -> None:
    print("\n== Disparity-filter backbone (Finding 3, 'no hub') ===============")
    for label, edges, runs in (("Family 1", e1, r1), ("Family 2", e2, r2)):
        m = point_to_point(edges)
        for n_agents in (4, 8):
            ids = runs[(runs.agent_count == n_agents)
                       & (runs.topology == "peer")
                       & (runs.artefact_policy == "allowed")].run_id
            sub = m[m.run_id.isin(ids)]
            if sub.empty:
                continue
            kept = total = 0
            for _, g in sub.groupby("run_id"):
                pairs = Counter(zip(g.source, g.target))
                total += len(pairs)
                kept += len(disparity_backbone(pairs, 0.05))
            share = 100 * kept / total if total else float("nan")
            report(f"{label}, n={n_agents}: backbone share at alpha=0.05",
                   f"{kept}/{total} edges ({share:.1f}%)")
    print("      Paper: 'a disparity-filter backbone of the message graph")
    print("      retains essentially no edges: no agent carries a")
    print("      disproportionate share.'")


def h6_addressing(e2: pd.DataFrame, r2: pd.DataFrame) -> None:
    print("\n== H6: does a shared constant reduce peer-directed addressing? ===")
    base = r2[(r2.instance == "summarise_transactions/clean")
              & (r2.agent_count == 4) & (r2.topology == "peer")
              & (r2.artefact_policy == "allowed")].run_id
    v2 = r2[r2.instance == "summarise_transactions_v2/clean"].run_id

    def canonical_share(ids):
        m = e2[(e2.run_id.isin(ids)) & (e2.edge_type == "agent_to_agent")]
        if m.empty:
            return float("nan")
        return 100 * (m.target_kind == "canonical").sum() / len(m)

    a, b = canonical_share(base), canonical_share(v2)
    check("H6 canonical addressing share (base -> v2)",
          f"{a:.1f} -> {b:.1f}", "28.3 -> 24.2")

    # The registered test (memory/experiments/family-2-full/analysis-plan.md)
    # is Fisher's exact on the POOLED canonical / non-canonical edge counts,
    # one-sided (v2 < summarise_transactions). A per-run rank test is a
    # different estimator and gives a different answer, so use the registered
    # one.
    def counts(ids):
        m = e2[(e2.run_id.isin(ids)) & (e2.edge_type == "agent_to_agent")]
        canonical = int((m.target_kind == "canonical").sum())
        return canonical, int(len(m) - canonical)

    bc, bn = counts(base)
    vc, vn = counts(v2)
    p = stats.fisher_exact([[vc, vn], [bc, bn]], alternative="less")[1]
    check("H6 significance (Fisher exact, one-sided, pooled counts)",
          f"p={p:.2f}", "p=0.23",
          "Registered test. Reported in the paper as not supported.")


def exploratory_regression(r1: pd.DataFrame) -> None:
    print("\n== Exploratory run-level association (paper: R^2 about 0.1) ======")
    d = r1[r1.agent_count > 1].copy()
    d = d[d.n_edges > 0]
    X = np.column_stack([
        np.log1p(d.n_agent_to_agent), np.log1p(d.n_agent_to_file),
        np.log1p(d.n_file_to_agent), d.agent_count,
    ])
    X = np.column_stack([np.ones(len(X)), X])
    y = d.success.astype(float).values
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    pred = X @ beta
    ss_res = ((y - pred) ** 2).sum()
    ss_tot = ((y - y.mean()) ** 2).sum()
    report("R^2, success on messaging/writing/reading + team size",
           f"{1 - ss_res / ss_tot:.3f}",
           "The paper says these associations explain about a tenth of the "
           "variance. This linear proxy is not the paper's model (that was a "
           "run-level logistic fit), so treat the value as indicative and "
           "read the paper's own hedge: the direction is exploratory and the "
           "causality is open.")


def main() -> int:
    e1 = pd.read_csv(D("family-1-full", "edges.csv"))
    r1 = pd.read_csv(D("family-1-full", "runs.csv"))
    e2 = pd.read_csv(D("family-2-full", "edges.csv"))
    r2 = pd.read_csv(D("family-2-full", "runs.csv"))

    centralisation_contrast(e1, r1)
    disparity_filter_backbone(e1, r1, e2, r2)
    h6_addressing(e2, r2)
    exploratory_regression(r1)

    print("\n" + "=" * 74)
    passed, total = sum(_results), len(_results)
    print(f"RESULT: {passed}/{total} recomputable checks passed")
    print("INFO lines are quantities the paper states qualitatively; they are")
    print("printed for inspection rather than asserted against a fixed value.")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
