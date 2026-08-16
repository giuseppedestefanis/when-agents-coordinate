#!/usr/bin/env python3
"""RQ1 structure and RQ3 structure-outcome analysis.

Implements the plan in
`memory/experiments/structure-outcome/analysis-plan.md`: the RQ1 structural
battery (degree by node type, read/write asymmetry, edge-type proportions,
and clustering / modularity / centralisation on the agent-agent message
subgraph) and the RQ3 structure-outcome regressions (a logistic
topology x pattern interaction, and run-level network-statistic -> outcome
models for success, completion time and a graded quality score).

These analyses are exploratory/descriptive, separate from the pre-registered
confirmatory tests (H1-H7). The script reads `edges.csv` and `runs.csv`
(ledger-filtered), joins a graded quality from the ledger's test counts, and
writes a markdown report per family under the experiment directory.

    .venv/bin/python scripts/analyse_structure_outcome.py \
        --experiment-root data/family-1-full \
        --out memory/experiments/structure-outcome/family-1-preliminary.md
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import networkx as nx
import numpy as np
import pandas as pd
import scipy.stats as ss
import statsmodels.formula.api as smf

from agent_comms.parser.datasets import combine_datasets


RUN_RE = re.compile(
    r"^family-(?P<family>\d+)-(?P<task>[a-z_0-9]+)"
    r"-(?P<pattern>clean|overlapping|conflicting)"
    r"-a(?P<agents>\d+)-(?P<topology>solo|peer|orchestrator)"
    r"-(?P<policy>forbidden|allowed|mandatory)-r(?P<rep>\d+)$"
)
NET_COUNTS = ("n_agent_to_agent", "n_agent_to_file", "n_file_to_agent")


def parse_run_id(run_id):
    m = RUN_RE.match(run_id)
    if not m:
        return None
    return {"family": m["family"], "task": m["task"], "pattern": m["pattern"],
            "agent_count": int(m["agents"]), "topology": m["topology"],
            "artefact_policy": m["policy"], "rep": int(m["rep"])}


def load_ledger(ledger_path):
    """Return (ok_run_ids, {run_id: quality or nan})."""
    if not os.path.exists(ledger_path):
        return set(), {}
    with open(ledger_path) as f:
        ledger = json.load(f)
    rows = (ledger["runs"] if isinstance(ledger, dict)
            and isinstance(ledger.get("runs"), list)
            else list(ledger.values()) if isinstance(ledger, dict) else ledger)
    ok, quality = set(), {}
    for r in rows:
        rid = r.get("run_id")
        if not rid or r.get("status") != "ok":
            continue
        ok.add(rid)
        p = r.get("tests_passed")
        fch = r.get("tests_failed")
        denom = (p or 0) + (fch or 0)
        quality[rid] = (p / denom) if denom else math.nan
    return ok, quality


def load_edges_by_run(edges_csv, ok):
    by_run = defaultdict(list)
    if not os.path.exists(edges_csv):
        return by_run
    with open(edges_csv, newline="") as f:
        for row in csv.DictReader(f):
            if ok and row.get("run_id") not in ok:
                continue
            by_run[row["run_id"]].append(row)
    return by_run


def load_runs(runs_csv, ok):
    rows = {}
    if not os.path.exists(runs_csv):
        return rows
    with open(runs_csv, newline="") as f:
        for row in csv.DictReader(f):
            rid = row["run_id"]
            if ok and rid not in ok:
                continue
            rows[rid] = row
    return rows


def _freeman_degree_centralisation(ug):
    """Freeman centralisation of undirected degree: 0 flat, 1 star."""
    n = ug.number_of_nodes()
    if n < 3:
        return math.nan
    deg = dict(ug.degree())
    ci = {v: d / (n - 1) for v, d in deg.items()}
    cmax = max(ci.values())
    return sum(cmax - c for c in ci.values()) / (n - 2)


def structural_metrics(edges):
    """Per-run RQ1 structural battery."""
    a2a_all = [e for e in edges if e["edge_type"] == "agent_to_agent"]
    a2f = [e for e in edges if e["edge_type"] == "agent_to_file"]
    f2a = [e for e in edges if e["edge_type"] == "file_to_agent"]
    n_a2a, n_a2f, n_f2a = len(a2a_all), len(a2f), len(f2a)
    tot = n_a2a + n_a2f + n_f2a
    out = {"n_a2a": n_a2a, "n_a2f": n_a2f, "n_f2a": n_f2a}
    out["prop_a2a"] = n_a2a / tot if tot else math.nan
    out["prop_a2f"] = n_a2f / tot if tot else math.nan
    out["prop_f2a"] = n_f2a / tot if tot else math.nan
    out["rw_asymmetry"] = n_f2a / n_a2f if n_a2f else math.nan
    # Share of messages that are point-to-point vs broadcast (one-to-many).
    out["prop_broadcast"] = (
        sum(1 for e in a2a_all if e.get("target_kind") == "broadcast") / n_a2a
        if n_a2a else math.nan)

    # File degree: a2f target is the file (writes received); f2a source is
    # the file (reads served).
    writes = Counter(e["target"] for e in a2f)
    reads = Counter(e["source"] for e in f2a)
    out["mean_file_in"] = (sum(writes.values()) / len(writes)
                           if writes else math.nan)
    out["mean_file_out"] = (sum(reads.values()) / len(reads)
                            if reads else math.nan)

    # Agent-agent coordination subgraph: point-to-point messages only
    # (target_kind canonical or alias, so both endpoints are agents), with
    # self-loops removed. Broadcast/role/unknown targets are not nodes here;
    # their volume is captured by prop_broadcast above. This keeps density
    # and centralisation in [0, 1].
    directed = [(e["source"], e["target"]) for e in a2a_all
                if e.get("target_kind") in ("canonical", "alias")
                and e["source"] != e["target"]]
    dg = nx.DiGraph()
    for (s, t), w in Counter(directed).items():
        dg.add_edge(s, t, weight=w)
    n = dg.number_of_nodes()
    out["a2a_nodes"] = n
    out["a2a_density"] = nx.density(dg) if n >= 2 else math.nan
    if n >= 3:
        ug = dg.to_undirected()
        out["a2a_clustering"] = nx.average_clustering(ug)
        comms = nx.community.greedy_modularity_communities(ug)
        out["a2a_modularity"] = nx.community.modularity(ug, comms)
        out["a2a_ncomm"] = len(comms)
        out["a2a_centralisation"] = _freeman_degree_centralisation(ug)
        bc = nx.betweenness_centrality(dg)
        out["a2a_max_betweenness"] = max(bc.values()) if bc else math.nan
    else:
        for k in ("a2a_clustering", "a2a_modularity", "a2a_ncomm",
                  "a2a_centralisation", "a2a_max_betweenness"):
            out[k] = math.nan
    return out


RQ1_SCALARS = ("prop_a2a", "prop_a2f", "prop_f2a", "rw_asymmetry",
               "mean_file_in", "mean_file_out", "a2a_density",
               "a2a_clustering", "a2a_modularity", "a2a_centralisation",
               "a2a_max_betweenness")


def _agg(vals):
    xs = [v for v in vals if v is not None and not (
        isinstance(v, float) and math.isnan(v))]
    if not xs:
        return (math.nan, math.nan, 0)
    mean = sum(xs) / len(xs)
    sd = (sum((x - mean) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5 \
        if len(xs) > 1 else 0.0
    return (mean, sd, len(xs))


def build_frame(by_run, runs, quality):
    """One row per run: parts + outcomes + network counts + structure."""
    records = []
    for rid, edges in by_run.items():
        parts = parse_run_id(rid)
        if parts is None or rid not in runs:
            continue
        r = runs[rid]
        rec = dict(parts)
        rec["run_id"] = rid
        rec["success"] = 1 if str(r.get("success", "")).lower() == "true" else 0
        try:
            rec["completion_time_s"] = float(r["completion_time_s"])
        except (KeyError, ValueError, TypeError):
            rec["completion_time_s"] = math.nan
        rec["quality"] = quality.get(rid, math.nan)
        for c in NET_COUNTS:
            try:
                rec[c] = float(r[c])
            except (KeyError, ValueError, TypeError):
                rec[c] = math.nan
        rec.update(structural_metrics(edges))
        records.append(rec)
    return pd.DataFrame.from_records(records)


# ---- RQ1 report ----

def rq1_section(df):
    lines = ["## RQ1 structural metrics (per cell: mean (sd))", ""]
    lines.append("Degree by node type: `f_in` = mean file in-degree (writes "
                 "received), `f_out` = mean file out-degree (reads served), "
                 "`rw_asym` = reads/writes. `bcast` = share of messages sent "
                 "as broadcast. A2A metrics are on the agent-agent "
                 "point-to-point message subgraph (self-loops and "
                 "broadcast/role targets excluded); `dens`/`clus`/`mod`/`centr` "
                 "= density / clustering / modularity / degree centralisation, "
                 "the last three needing >= 3 messaging agents, so solo and "
                 "most 2-agent cells are n/a (expected).")
    lines.append("")
    cols = ("| cell | n | prop_a2a | bcast | f_in | f_out | rw_asym "
            "| dens | clus | mod | centr |")
    lines.append(cols)
    lines.append("|" + "---|" * 11)
    keycols = ["agent_count", "topology", "artefact_policy", "pattern", "task"]
    for key, g in df.groupby(keycols):
        a, topo, pol, pat, task = key
        label = f"a{a}-{topo}-{pol}-{pat}"
        if task not in ("process_orders", "summarise_transactions"):
            label += f"/{task}"

        def f(col):
            m, sd, k = _agg(g[col].tolist())
            return "n/a" if math.isnan(m) else f"{m:.2f} ({sd:.2f})"
        lines.append(
            f"| {label} | {len(g)} | {f('prop_a2a')} | {f('prop_broadcast')} "
            f"| {f('mean_file_in')} | {f('mean_file_out')} "
            f"| {f('rw_asymmetry')} | {f('a2a_density')} "
            f"| {f('a2a_clustering')} | {f('a2a_modularity')} "
            f"| {f('a2a_centralisation')} |")
    lines.append("")
    return lines


# ---- 5.1 descriptive target_kind share ranges ----

def target_kind_share_ranges(by_run):
    """5.1 descriptive target_kind share ranges (broadcast and role).

    Definition (one documented rule, applied uniformly):

      * A *cell* is one (agent_count, topology, artefact_policy, pattern)
        combination.
      * A cell's share of a target_kind is the message-weighted (pooled-edge)
        share: (sum of agent_to_agent edges of that kind in the cell) divided
        by (sum of all agent_to_agent edges in the cell), pooled over the
        cell's ok runs. This is the same per-cell pooled share that
        analyse_family2_full's summarise_cell emits.
      * The reported range is the min-max of those per-cell pooled shares
        across the cells in the named slice (an agent-count, optionally a
        policy). Cells with no agent_to_agent edges are excluded.

    Run on the Family-1 root this yields the 5.1 F1 broadcast-by-n rows; on the
    Family-2 root it yields the F2 broadcast (n=4, n=8) and role (per n x
    policy, e.g. n=4 mandatory) rows. The per-run-mean alternative (mean of
    per-run shares, then range over cells) is noted in the report for context.
    """
    cell_kind = defaultdict(lambda: defaultdict(int))
    cell_tot = defaultdict(int)
    cell_runshares = defaultdict(lambda: defaultdict(list))  # cell->kind->[per-run shares]
    for rid, edges in by_run.items():
        parts = parse_run_id(rid)
        if parts is None:
            continue
        cell = (parts["agent_count"], parts["topology"],
                parts["artefact_policy"], parts["pattern"])
        a2a = [e for e in edges if e["edge_type"] == "agent_to_agent"]
        cell_tot[cell] += len(a2a)
        run_kind = Counter(e.get("target_kind", "") for e in a2a)
        for k, c in run_kind.items():
            cell_kind[cell][k] += c
        if a2a:
            for k in ("broadcast", "role"):
                cell_runshares[cell][k].append(run_kind.get(k, 0) / len(a2a))

    def pooled_shares(kind, n=None, policy=None):
        out = []
        for cell, tot in cell_tot.items():
            cn, _topo, cpol, _pat = cell
            if n is not None and cn != n:
                continue
            if policy is not None and cpol != policy:
                continue
            if tot <= 0:
                continue
            out.append(cell_kind[cell][kind] / tot)
        return out

    def perrun_mean_shares(kind, n=None, policy=None):
        out = []
        for cell, byk in cell_runshares.items():
            cn, _topo, cpol, _pat = cell
            if n is not None and cn != n:
                continue
            if policy is not None and cpol != policy:
                continue
            vals = byk.get(kind, [])
            if vals:
                out.append(sum(vals) / len(vals))
        return out

    ns = sorted({c[0] for c in cell_tot})
    lines = ["## RQ1 / 5.1 target_kind share ranges "
             "(pooled-edge per (agent_count, topology, policy, pattern) cell)",
             ""]
    lines.append("Per-cell share = message-weighted (pooled-edge) share of the "
                 "target_kind among agent-to-agent edges, pooled over the "
                 "cell's ok runs; range = min-max across the cells in the "
                 "slice. The bracketed value is the per-run-mean alternative "
                 "(mean of per-run shares, then min-max over cells).")
    lines.append("")
    lines.append("| kind | slice | cells | pooled-edge range | "
                 "[per-run-mean range] |")
    lines.append("|---|---|---|---|---|")

    def emit(kind, label, n=None, policy=None):
        p = pooled_shares(kind, n=n, policy=policy)
        m = perrun_mean_shares(kind, n=n, policy=policy)
        if not p:
            return
        prng = f"{min(p)*100:.1f}%-{max(p)*100:.1f}%"
        mrng = (f"{min(m)*100:.1f}%-{max(m)*100:.1f}%" if m else "n/a")
        lines.append(f"| {kind} | {label} | {len(p)} | {prng} | [{mrng}] |")

    for n in ns:
        emit("broadcast", f"n={n} (topo x policy x pattern)", n=n)
    for n in ns:
        for pol in ("forbidden", "allowed", "mandatory"):
            emit("role", f"n={n} {pol} (topo x pattern)", n=n, policy=pol)
    lines.append("")
    return lines


# ---- Committed contrast (methods commit to this specific test) ----

def centralisation_contrast(df):
    """Mann-Whitney on A2A degree centralisation, peer vs orchestrator at
    n=8. The methods commit to this contrast; pooled across policies and
    patterns, then broken out per policy because the artefact policy strongly
    affects message volume (and so centralisation). Runs whose A2A subgraph
    has < 3 messaging agents have NaN centralisation and are dropped."""
    lines = ["## RQ1 committed contrast: degree centralisation, "
             "peer vs orchestrator (n=8)", ""]
    lines.append("Mann-Whitney U (two-sided) on A2A degree centralisation. "
                 "Pooled is the headline contrast; per-policy rows are shown "
                 "because under `mandatory` message volume collapses and the "
                 "few remaining messages inflate centralisation (a low-volume "
                 "artefact, not hub coordination).")
    lines.append("")
    lines.append("| subset | peer n (median) | orch n (median) | U | p |")
    lines.append("|---|---|---|---|---|")
    n8 = df[df["agent_count"] == 8]

    def row(sub, label):
        p = [v for v in sub[sub.topology == "peer"]["a2a_centralisation"]
             if not math.isnan(v)]
        o = [v for v in sub[sub.topology == "orchestrator"]["a2a_centralisation"]
             if not math.isnan(v)]
        if len(p) < 2 or len(o) < 2:
            lines.append(f"| {label} | peer n={len(p)} | orch n={len(o)} "
                         f"| n/a | n/a |")
            return
        u, pv = ss.mannwhitneyu(p, o, alternative="two-sided")
        lines.append(f"| {label} | {len(p)} ({np.median(p):.3f}) "
                     f"| {len(o)} ({np.median(o):.3f}) | {u:.1f} | {pv:.3g} |")

    row(n8, "pooled")
    for pol in ("allowed", "forbidden", "mandatory"):
        row(n8[n8.artefact_policy == pol], f"policy={pol}")
    lines.append("")
    return lines


# ---- RQ3 regressions ----

def _zscore(df, cols):
    out = df.copy()
    for c in cols:
        s = out[c]
        sd = s.std()
        out[c + "_z"] = (s - s.mean()) / sd if sd and not math.isnan(sd) \
            else 0.0
    return out


def _fit_summary(title, fit, terms=None):
    lines = [f"### {title}", ""]
    if fit is None:
        lines += ["(model did not converge / insufficient data)", ""]
        return lines
    lines.append(f"n = {int(fit.nobs)}; "
                 + (f"pseudo-R2 = {fit.prsquared:.3f}"
                    if hasattr(fit, "prsquared") else
                    f"R2 = {fit.rsquared:.3f}"))
    lines.append("")
    lines.append("| term | coef | p |")
    lines.append("|---|---|---|")
    params, pvals = fit.params, fit.pvalues
    keys = terms if terms else params.index
    for k in keys:
        if k in params.index:
            lines.append(f"| {k} | {params[k]:+.3f} | {pvals[k]:.3g} |")
    lines.append("")
    return lines


def _safe_logit(formula, data):
    try:
        return smf.logit(formula, data=data).fit(disp=False, maxiter=100)
    except Exception:
        return None


def _safe_ols(formula, data):
    try:
        return smf.ols(formula, data=data).fit()
    except Exception:
        return None


def rq3_section(df):
    lines = ["## RQ3 structure-outcome regressions (exploratory)", ""]
    lines.append("Predictors z-scored within the fitted sample; "
                 "`C(agent_count)` is a categorical control. Multicollinearity "
                 "among counts is expected; read for direction. Not "
                 "pre-registered; no multiple-comparison correction.")
    lines.append("")

    # Model 1: topology x pattern interaction, multi-agent peer/orchestrator.
    m1 = df[(df["agent_count"] >= 2)
            & (df["topology"].isin(["peer", "orchestrator"]))].copy()
    fit1 = _safe_logit("success ~ C(topology) * C(pattern)", m1) \
        if m1["success"].nunique() > 1 else None
    inter = [t for t in (fit1.params.index if fit1 is not None else [])
             if ":" in t]
    lines += _fit_summary(
        "Model 1: success ~ topology * pattern (interaction terms)",
        fit1, terms=inter or None)

    # Models 2-4: network-count statistics -> outcome, all runs. The counts
    # are defined for every run (a solo run has zero messages), so no row is
    # silently dropped; a2a_density is left to the RQ1 battery because it is
    # undefined for runs with no point-to-point messaging.
    base = _zscore(df.copy(), list(NET_COUNTS))
    pred_terms = [c + "_z" for c in NET_COUNTS]
    preds = " + ".join(pred_terms) + " + C(agent_count)"
    fit2 = _safe_logit(f"success ~ {preds}", base) \
        if base["success"].nunique() > 1 else None
    lines += _fit_summary("Model 2: success ~ network statistics", fit2,
                          terms=pred_terms)
    fit3 = _safe_ols(f"completion_time_s ~ {preds}", base)
    lines += _fit_summary("Model 3: completion_time_s ~ network statistics",
                          fit3, terms=pred_terms)
    q = base[~base["quality"].isna()].copy()
    n_drop = len(base) - len(q)
    fit4 = _safe_ols(f"quality ~ {preds}", q) if len(q) > 10 else None
    lines += _fit_summary(
        f"Model 4: quality ~ network statistics "
        f"(n={len(q)}, {n_drop} dropped for no graded tests)", fit4,
        terms=pred_terms)
    return lines


def main():
    ap = argparse.ArgumentParser(description="RQ1 structure + RQ3 regression.")
    ap.add_argument("--experiment-root", default="data/family-1-full")
    ap.add_argument("--out",
                    default="memory/experiments/structure-outcome/"
                            "family-1-preliminary.md")
    ap.add_argument("--combine", action="store_true")
    args = ap.parse_args()

    root = args.experiment_root
    master = os.path.join(root, "master")
    if args.combine:
        combine_datasets(os.path.join(root, "runs"), master)

    ok, quality = load_ledger(os.path.join(root, "ledger.json"))
    by_run = load_edges_by_run(os.path.join(master, "edges.csv"), ok)
    runs = load_runs(os.path.join(master, "runs.csv"), ok)
    df = build_frame(by_run, runs, quality)

    lines = [f"# RQ1 structure and RQ3 structure-outcome: {root}", ""]
    lines.append(f"Runs: {len(df)}. Definitions: "
                 "`memory/experiments/structure-outcome/analysis-plan.md`. "
                 "Exploratory/descriptive, not pre-registered confirmatory.")
    lines.append("")
    lines += rq1_section(df)
    lines += target_kind_share_ranges(by_run)
    lines += centralisation_contrast(df)
    lines += rq3_section(df)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"structure-outcome: {len(df)} runs -> {args.out}")


if __name__ == "__main__":
    main()
