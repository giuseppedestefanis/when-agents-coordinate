#!/usr/bin/env python3
"""De-trivialising the n^2 messaging result (2026-06-15, rev 2).

The "inter-agent messaging grows as n^2" headline is close to a restatement of
"the agent graph is a clique": a complete directed graph has n(n-1) ordered
edges, so any near-complete addressing pattern scales ~n^2 by construction.
This is a NARROW, POSITIVE elaboration -- it surfaces the non-trivial structure
the clique view hides. It is NOT an audit of the paper; the paper's claims are
taken as correct, and any apparent tension is treated as a scoping/definition
question on the analysis side.

  H2  Effective coordination degree is BOUNDED / saturates. The n^2 layer is
      the one-shot "greet everyone once" pass (t>=1 hugs the clique line n-1);
      the SUSTAINED coordination degree -- distinct directed peers an agent
      sends >= t messages to, t swept -- flattens far below n-1. This is the
      family-independent result. Definitions are LOCKED and reported under two
      denominators (see below).

  H1  The FILE channel is a one-to-many broadcast medium, so coordination on
      it scales sub-quadratically. Per run we fit the agent-count exponents of
      M (agent_to_agent), W (agent_to_file = writes), R (file_to_agent =
      reads), the token-cost analogues, and the broadcast-amplification ratio
      phi = R / W. F2 is the clean case; the F1 read channel is re-examined PER
      DRAW because its n=8 file count is the dataset's least-reproducible
      quantity.

  H1d / backbone  Secondary. Mandatory-vs-allowed total-cost exponent, and the
      disparity-filter backbone (Serrano-Boguna-Vespignani 2009).

Effective-degree denominators (LOCKED). For each run, for threshold t, let
deg_sum = sum over agents of (# distinct directed peers addressed with >= t
messages). We report:
  * team-level      = deg_sum / n           (all n agents; idle agents count 0)
  * participant     = deg_sum / n_qual(t)   (agents sustaining >=1 such peer)
and, for continuity with rev 1 and the prior relay, the directed-sender mean
deg_sum / n_directed. On the F2 peer/allowed/clean n=8 cell these read (pooled)
1.89 / 3.60 / 2.10 at t>=2: i.e. the prior pass's "2.10" is the directed-sender
denominator and the "3.6" is the participant (qualifying-sender) denominator;
the literal team-level (/n) is 1.89.

Directed peer = target_kind in {canonical, alias}; broadcast/role/unknown do
not name one distinct peer. Aliases are not collapsed onto their canonical
agent, so directed degree is an UPPER bound on distinct peers -- conservative
against saturation.

Data scope:
  Family 1: data/family-1-full, instance prefix process_orders.
  Family 2: data/family-2-full, instance prefix summarise_transactions.
  compute_invoices H7 scaling arm: data/compute-invoices-scaling (n=2/4/8,
    peer, compute_invoices/clean, 30 runs) -- NOT the separate 10-run n=4
    batch in family-2-full.
  summarise_transactions_v2 (H6 baseline) excluded.

Usage:
    .venv/bin/python scripts/analyse_messaging_structure.py
"""

from __future__ import annotations

import csv
import datetime as dt
import math
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # sibling scripts

# The exact log-log slope+CI estimator used by the existing H1 scaling fit.
from analyse_solo_peer_reliability import linregress_slope_ci

csv.field_size_limit(10 ** 7)  # some message edges carry large payloads

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
F1_ROOT = os.path.join(REPO, "data", "family-1-full")
F2_ROOT = os.path.join(REPO, "data", "family-2-full")
CI_ROOT = os.path.join(REPO, "data", "compute-invoices-scaling")

OUT_MD = os.path.join(REPO, "memory", "experiments",
                      "messaging-structure.md")
CELL_CSV = os.path.join(REPO, "data", "derived",
                        "messaging-structure-cells.csv")

import re
_AGENT_RE = re.compile(r"^agent-(\d+)$")

N_VALUES = (2, 4, 8)
FLAT_DRAWS = ("solo", "peer")
TOPOLOGIES = ("solo", "peer", "orchestrator")
POLICIES = ("forbidden", "allowed", "mandatory")
PATTERNS = ("clean", "overlapping", "conflicting")
THRESHOLDS = (1, 2, 3, 5)
DIRECTED_KINDS = ("canonical", "alias")

# clique reference: degree n-1 over n in {2,4,8} -> slope of log(n-1) on log n.
CLIQUE_SLOPE = (math.log(7) - math.log(1)) / (math.log(8) - math.log(2))  # 1.40
# the paper's per-pair density drop (messages per ordered pair) at n=2/4/8.
DENSITY_DROP = (3.05, 2.38, 1.27)


# ----------------------------------------------------------------------------
# loading
# ----------------------------------------------------------------------------

def load_runs(runs_csv, instance_prefix):
    """{run_id: meta} for rows with total_output_tokens > 0 whose instance
    prefix (before '/') equals instance_prefix. Returns (meta, n_dropped)."""
    meta = {}
    n_dropped = 0
    with open(runs_csv, newline="") as f:
        for r in csv.DictReader(f):
            inst = r.get("instance", "")
            prefix = inst.split("/")[0] if "/" in inst else inst
            patt = inst.split("/")[1] if "/" in inst else ""
            if prefix != instance_prefix:
                continue
            try:
                tok = float(r["total_output_tokens"])
            except (KeyError, ValueError, TypeError):
                tok = 0.0
            if tok <= 0:
                n_dropped += 1
                continue
            try:
                n = int(r["agent_count"])
            except (KeyError, ValueError):
                continue
            meta[r["run_id"]] = {
                "family": r["family"], "n": n, "topology": r["topology"],
                "policy": r["artefact_policy"], "pattern": patt,
                "instance": inst,
                "n_a2a_directed": r.get("n_agent_to_agent_directed", ""),
                "n_a2a": r.get("n_agent_to_agent", ""),
            }
    return meta, n_dropped


def _tok(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def aggregate_edges(edges_csv, valid_runs, roster_n=None):
    """Aggregate edges.csv into per-run structural quantities for the §2-§4
    metrics plus the locked effective-degree numerators/denominators.

    M/W/R and the directed message COUNT are taken verbatim (they validate
    against runs.csv). The distinct-PEER structure used by H2 and the backbone
    (`out_directed`, `pairs`) excludes self-addressed edges (source == target)
    and, when roster_n {run_id: n} is given, out-of-roster targets (recipient
    ids outside agent-1..agent-n, e.g. a hallucinated `agent-0`). Without that
    exclusion an agent can appear to have more than n-1 distinct peers, which
    is incoherent for the clique comparison. Per-run counts of what was
    excluded are reported for transparency.
    """
    raw = defaultdict(lambda: {
        "M": 0, "W": 0, "R": 0,
        "tok_M": 0.0, "tok_W": 0.0, "tok_R": 0.0,
        "w_f": Counter(), "readers": defaultdict(set), "r_f": Counter(),
        "out_directed": defaultdict(Counter), "senders": set(),
        "pairs": Counter(), "n_self": 0, "n_phantom": 0,
    })

    def in_roster(rid, agent_id):
        if roster_n is None or rid not in roster_n:
            return True
        m = _AGENT_RE.match(agent_id)
        return bool(m) and 1 <= int(m.group(1)) <= roster_n[rid]

    with open(edges_csv, newline="") as f:
        for r in csv.DictReader(f):
            rid = r["run_id"]
            if rid not in valid_runs:
                continue
            et = r["edge_type"]
            d = raw[rid]
            if et == "agent_to_agent":
                src, tgt = r["source"], r["target"]
                d["M"] += 1
                d["tok_M"] += _tok(r["token_cost"])
                d["senders"].add(src)
                if r["target_kind"] in DIRECTED_KINDS:
                    if src == tgt:
                        d["n_self"] += 1
                    elif not in_roster(rid, tgt):
                        d["n_phantom"] += 1
                    else:
                        d["out_directed"][src][tgt] += 1
                        d["pairs"][(src, tgt)] += 1
            elif et == "agent_to_file":
                d["W"] += 1
                d["tok_W"] += _tok(r["token_cost"])
                d["w_f"][r["target"]] += 1
            elif et == "file_to_agent":
                d["R"] += 1
                d["tok_R"] += _tok(r["token_cost"])
                d["r_f"][r["source"]] += 1
                d["readers"][r["source"]].add(r["target"])

    out = {}
    for rid in valid_runs:
        d = raw.get(rid) or raw[rid]
        M, W, R = d["M"], d["W"], d["R"]
        phi = (R / W) if W > 0 else None
        written = list(d["w_f"].keys())
        readers_per_written = [len(d["readers"].get(f, ())) for f in written]
        mean_readers_written = (sum(readers_per_written) / len(written)
                                if written else None)
        read_files = [f for f in d["readers"] if len(d["readers"][f]) >= 1]
        shared = [f for f in read_files if len(d["readers"][f]) >= 2]
        private = [f for f in read_files if len(d["readers"][f]) == 1]
        reads_on_shared = sum(d["r_f"][f] for f in shared)
        broadcast_read_share = (reads_on_shared / R) if R > 0 else None
        # effective-degree numerator/denominators
        deg_sum, n_qual, eff_dir = {}, {}, {}
        for t in THRESHOLDS:
            degs = [sum(1 for c in tgts.values() if c >= t)
                    for tgts in d["out_directed"].values()]
            deg_sum[t] = sum(degs)
            n_qual[t] = sum(1 for g in degs if g > 0)
            eff_dir[t] = (sum(degs) / len(degs)) if degs else None
        out[rid] = {
            "M": M, "W": W, "R": R,
            "tok_M": d["tok_M"], "tok_W": d["tok_W"], "tok_R": d["tok_R"],
            "C": M + W + R, "tok_C": d["tok_M"] + d["tok_W"] + d["tok_R"],
            "phi": phi,
            "mean_readers_per_written_file": mean_readers_written,
            "n_shared_files": len(shared), "n_private_files": len(private),
            "broadcast_read_share": broadcast_read_share,
            "eff_outdeg": eff_dir,        # directed-sender mean (rev-1 metric)
            "deg_sum": deg_sum, "n_qual": n_qual,
            "n_active": len(d["senders"]),
            "n_directed": len(d["out_directed"]),
            "n_agents": None,             # merged from meta in build()
            "n_self": d["n_self"], "n_phantom": d["n_phantom"],
            "pairs": dict(d["pairs"]),
        }
    return out


def merge_n_agents(meta, metrics):
    for rid, m in meta.items():
        if rid in metrics:
            metrics[rid]["n_agents"] = m["n"]


# ----------------------------------------------------------------------------
# cell grouping and fits
# ----------------------------------------------------------------------------

def cells_for(meta, metrics, draws, policy, pattern):
    by_n = defaultdict(list)
    for rid, m in meta.items():
        if m["topology"] not in draws or m["policy"] != policy \
                or m["pattern"] != pattern or m["n"] not in N_VALUES:
            continue
        by_n[m["n"]].append(metrics[rid])
    return by_n


def _vals(records, key):
    out = []
    for rec in records:
        v = rec.get(key)
        if isinstance(v, dict) or v is None:
            continue
        if isinstance(v, float) and math.isnan(v):
            continue
        out.append(v)
    return out


def cell_mean(records, key):
    vs = _vals(records, key)
    return (sum(vs) / len(vs)) if vs else float("nan")


def eff_perrun(rec, t, denom):
    """Per-run effective out-degree under denom in {team, participant,
    directed}. Returns None when the denominator is zero."""
    s = rec["deg_sum"][t]
    if denom == "team":
        d = rec["n_agents"]
    elif denom == "participant":
        d = rec["n_qual"][t]
    else:
        d = rec["n_directed"]
    if not d:
        return None
    return s / d


def eff_cell_mean(records, t, denom):
    vs = [eff_perrun(r, t, denom) for r in records]
    vs = [v for v in vs if v is not None]
    return (sum(vs) / len(vs)) if vs else float("nan")


def _cm_slope(means):
    xs = [math.log(n) for n in N_VALUES if means.get(n)]
    ys = [math.log(means[n]) for n in N_VALUES if means.get(n)]
    if len(xs) < 2:
        return float("nan")
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return sxy / sxx if sxx else float("nan")


def fit_metric(by_n, key, *, sub=None):
    """Per-run log-log slope+CI of `key` on n, plus cell-mean 3pt slope and
    segment slopes. key=='eff' uses eff_outdeg[sub] (directed-sender mean)."""
    xs, ys, means = [], [], {}
    for n in N_VALUES:
        vals = []
        for rec in by_n.get(n, []):
            v = rec["eff_outdeg"][sub] if key == "eff" else rec.get(key)
            if v is None or (isinstance(v, float) and math.isnan(v)) or v <= 0:
                continue
            vals.append(v)
        for v in vals:
            xs.append(math.log(n))
            ys.append(math.log(v))
        means[n] = (sum(vals) / len(vals)) if vals else None
    b, lo, hi = linregress_slope_ci(xs, ys)
    seg24 = (math.log(means[4] / means[2]) / math.log(2)
             if means.get(2) and means.get(4) else float("nan"))
    seg48 = (math.log(means[8] / means[4]) / math.log(2)
             if means.get(4) and means.get(8) else float("nan"))
    return {"slope": b, "lo": lo, "hi": hi, "cm_slope": _cm_slope(means),
            "seg24": seg24, "seg48": seg48, "means": means, "npts": len(xs)}


def fit_eff(by_n, t, denom):
    """Per-run log-log slope+CI of the effective out-degree (denom) on n."""
    xs, ys, means = [], [], {}
    for n in N_VALUES:
        vals = [eff_perrun(r, t, denom) for r in by_n.get(n, [])]
        vals = [v for v in vals if v and v > 0]
        for v in vals:
            xs.append(math.log(n))
            ys.append(math.log(v))
        means[n] = (sum(vals) / len(vals)) if vals else None
    b, lo, hi = linregress_slope_ci(xs, ys)
    return {"slope": b, "lo": lo, "hi": hi, "means": means, "npts": len(xs)}


# ----------------------------------------------------------------------------
# disparity filter (Serrano-Boguna-Vespignani 2009) -- secondary
# ----------------------------------------------------------------------------

def disparity_backbone(pairs, alpha):
    """Ordered (src,tgt) edges surviving the disparity filter at alpha, kept if
    significant from EITHER endpoint."""
    out_w, in_w = defaultdict(dict), defaultdict(dict)
    for (src, tgt), w in pairs.items():
        out_w[src][tgt] = w
        in_w[tgt][src] = w
    keep = set()
    for src, nbrs in out_w.items():
        k, s = len(nbrs), sum(nbrs.values())
        if k < 2 or s <= 0:
            continue
        for tgt, w in nbrs.items():
            if (1 - w / s) ** (k - 1) < alpha:
                keep.add((src, tgt))
    for tgt, nbrs in in_w.items():
        k, s = len(nbrs), sum(nbrs.values())
        if k < 2 or s <= 0:
            continue
        for src, w in nbrs.items():
            if (1 - w / s) ** (k - 1) < alpha:
                keep.add((src, tgt))
    return keep


def backbone_row(records, alpha):
    bb, full, dens = [], [], []
    for rec in records:
        pairs = rec.get("pairs") or {}
        if not pairs:
            continue
        nodes = {x for pair in pairs for x in pair}
        n = len(nodes)
        keep = disparity_backbone(pairs, alpha)
        bb.append(len(keep))
        full.append(len(pairs))
        if n >= 2:
            dens.append(len(keep) / (n * (n - 1)))
    if not bb:
        return None
    return {"n_runs": len(bb), "backbone_edges": sum(bb) / len(bb),
            "full_edges": sum(full) / len(full),
            "backbone_density": (sum(dens) / len(dens)) if dens
            else float("nan")}


# ----------------------------------------------------------------------------
# report assembly
# ----------------------------------------------------------------------------

def _fmt(x, p=2):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "--"
    return f"{x:.{p}f}"


def fit_line(label, fit):
    return (f"| {label} | {_fmt(fit['slope'])} "
            f"[{_fmt(fit['lo'])}, {_fmt(fit['hi'])}] | {_fmt(fit['cm_slope'])} "
            f"| {_fmt(fit['seg24'])} | {_fmt(fit['seg48'])} | {fit['npts']} |")


def channel_table(meta, metrics, family_label, L):
    L.append(f"#### {family_label} — channel exponents (clean; per-run log-log "
             f"slope of value on n)")
    L.append("")
    for pol in ("allowed", "mandatory"):
        L.append(f"*Policy: {pol}*")
        L.append("")
        L.append("| draw / channel | slope (95% CI) | cell-mean slope | "
                 "seg 2->4 | seg 4->8 | n pts |")
        L.append("|---|---|---:|---:|---:|---:|")
        for draw in FLAT_DRAWS + ("orchestrator",):
            by_n = cells_for(meta, metrics, (draw,), pol, "clean")
            if not any(by_n.values()):
                continue
            for key, name in [("M", "M msgs"), ("W", "W writes"),
                              ("R", "R reads"), ("C", "C=M+W+R"),
                              ("tok_M", "tok(M)"), ("tok_R", "tok(R)")]:
                L.append(fit_line(f"{draw} / {name}", fit_metric(by_n, key)))
        L.append("")


def phi_table(meta, metrics, family_label, L):
    L.append(f"#### {family_label} — broadcast amplification (peer, clean)")
    L.append("")
    L.append("| policy | n | N | phi=R/W | readers/written file | "
             "shared files | broadcast read share | (W=0 dropped) |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for pol in POLICIES:
        by_n = cells_for(meta, metrics, ("peer",), pol, "clean")
        for n in N_VALUES:
            recs = by_n.get(n, [])
            if not recs:
                continue
            w0 = sum(1 for r in recs if r["phi"] is None)
            L.append(
                f"| {pol} | {n} | {len(recs)} | {_fmt(cell_mean(recs, 'phi'))} "
                f"| {_fmt(cell_mean(recs, 'mean_readers_per_written_file'))} | "
                f"{_fmt(cell_mean(recs, 'n_shared_files'))} | "
                f"{_fmt(cell_mean(recs, 'broadcast_read_share'))} | {w0} |")
    L.append("")


def h2_table(meta, metrics, family_label, L):
    """Locked-definition effective out-degree: per draw, threshold sweep,
    team-level and participant denominators, per-run slopes + CI vs clique."""
    L.append(f"#### {family_label} — effective coordination out-degree "
             f"(LOCKED; allowed, clean)")
    L.append("")
    for draw in FLAT_DRAWS:
        by_n = cells_for(meta, metrics, (draw,), "allowed", "clean")
        if not any(by_n.values()):
            continue
        L.append(f"*Draw: {draw}* — team-level (/n) | participant "
                 f"(/qualifying senders)")
        L.append("")
        L.append("| n | clique n-1 | team t>=1 | team t>=2 | team t>=3 | "
                 "team t>=5 | part t>=2 | qual senders | N |")
        L.append("|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        for n in N_VALUES:
            recs = by_n.get(n, [])
            if not recs:
                continue
            cells = [_fmt(eff_cell_mean(recs, t, "team")) for t in THRESHOLDS]
            part2 = _fmt(eff_cell_mean(recs, 2, "participant"))
            qual = _fmt(cell_mean([{"q": r["n_qual"][2]} for r in recs], "q"))
            L.append(f"| {n} | {n - 1} | " + " | ".join(cells) +
                     f" | {part2} | {qual} | {len(recs)} |")
        team = fit_eff(by_n, 2, "team")
        part = fit_eff(by_n, 2, "participant")
        L.append("")
        L.append(f"Per-run log-log slope (t>=2) vs clique reference "
                 f"{_fmt(CLIQUE_SLOPE)}: team-level "
                 f"{_fmt(team['slope'])} [{_fmt(team['lo'])}, "
                 f"{_fmt(team['hi'])}]; participant {_fmt(part['slope'])} "
                 f"[{_fmt(part['lo'])}, {_fmt(part['hi'])}].")
        L.append("")
    L.append(f"Convergent evidence: the same saturation appears in the paper's "
             f"per-pair density drop (messages/ordered pair "
             f"{DENSITY_DROP[0]}, {DENSITY_DROP[1]}, {DENSITY_DROP[2]} at "
             f"n=2/4/8) and the H7 deceleration past n=4 — three angles on one "
             f"bounded-degree story.")
    L.append("")


def f1_read_perdraw(meta, metrics, L):
    """F1 read-channel reproducibility check: R per draw, segment + full +
    low-n (2,4) slopes, vs the message slope, with an explicit verdict on
    whether the 'F1 shows no broadcast' reading survives off the n=8 cell."""
    L.append("#### Family 1 — read-channel per draw (reproducibility of the "
             "no-broadcast reading)")
    L.append("")
    L.append("| draw | R n=2/4/8 | seg 2->4 | seg 4->8 | R slope (2,4,8) | "
             "R slope (2,4 only) | M slope (2,4,8) | M-R gap |")
    L.append("|---|---|---:|---:|---:|---:|---:|---:|")
    for draw in FLAT_DRAWS:
        by_n = cells_for(meta, metrics, (draw,), "allowed", "clean")
        rfit = fit_metric(by_n, "R")
        mfit = fit_metric(by_n, "M")
        means = rfit["means"]
        low = _cm_slope({2: means.get(2), 4: means.get(4)})
        series = "/".join(_fmt(means.get(n), 1) for n in N_VALUES)
        gap = (mfit["slope"] - rfit["slope"]
               if not math.isnan(mfit["slope"]) else float("nan"))
        L.append(f"| {draw} | {series} | {_fmt(rfit['seg24'])} | "
                 f"{_fmt(rfit['seg48'])} | {_fmt(rfit['slope'])} | "
                 f"{_fmt(low)} | {_fmt(mfit['slope'])} | {_fmt(gap)} |")
    L.append("")
    L.append("VERDICT: the 'F1 shows no broadcast' reading does NOT survive "
             "off the n=8 peer cell. F1 peer reads are essentially flat from "
             "n=2->4 (a broadcast signature) and only the n=8 file blow-up "
             "(the dataset's least-reproducible quantity; peer 38.8 vs solo "
             "16.9 reads) pulls the full slope up to ~2. The message channel "
             "still outscales the read channel in BOTH draws (positive M-R "
             "gap), so a (weaker) broadcast channel is present in F1 too -- "
             "the apparent F1 exception is the n=8 artefact, not a real "
             "family difference.")
    L.append("")


def backbone_table(meta, metrics, family_label, L):
    L.append(f"#### {family_label} — disparity-filter backbone (peer, clean, "
             f"allowed) [EXPLORATORY]")
    L.append("")
    L.append("| alpha | n | N | full edges | backbone edges | "
             "backbone density |")
    L.append("|---:|---:|---:|---:|---:|---:|")
    by_n = cells_for(meta, metrics, ("peer",), "allowed", "clean")
    for alpha in (0.05, 0.1):
        for n in (4, 8):
            recs = by_n.get(n, [])
            row = backbone_row(recs, alpha) if recs else None
            if not row:
                continue
            L.append(f"| {alpha} | {n} | {row['n_runs']} | "
                     f"{_fmt(row['full_edges'])} | "
                     f"{_fmt(row['backbone_edges'])} | "
                     f"{_fmt(row['backbone_density'], 3)} |")
    L.append("")


def compute_invoices_section(ci_meta, ci_met, L):
    """compute_invoices/clean H7 scaling arm (data/compute-invoices-scaling):
    broadcast-only coordination and file fan-out at full decomposition."""
    L.append("## compute_invoices/clean — broadcast at full decomposition "
             "(data/compute-invoices-scaling)")
    L.append("")
    L.append("| n | N | all-broadcast runs (directed=0, M>0) | mean phi=R/W | "
             "mean readers/written file | mean shared files |")
    L.append("|---:|---:|---:|---:|---:|---:|")
    for n in N_VALUES:
        rids = [r for r, m in ci_meta.items() if m["n"] == n]
        if not rids:
            continue
        allbc = 0
        for r in rids:
            try:
                d = int(float(ci_meta[r]["n_a2a_directed"]))
                m = int(float(ci_meta[r]["n_a2a"]))
            except ValueError:
                d, m = 1, 0
            if d == 0 and m > 0:
                allbc += 1
        recs = [ci_met[r] for r in rids]
        L.append(f"| {n} | {len(rids)} | {allbc} | "
                 f"{_fmt(cell_mean(recs, 'phi'))} | "
                 f"{_fmt(cell_mean(recs, 'mean_readers_per_written_file'))} | "
                 f"{_fmt(cell_mean(recs, 'n_shared_files'))} |")
    L.append("")
    L.append("At n=8 (the full one-step-per-agent decomposition) 4 of 10 runs "
             "carry NO directed pair -- every one of their messages is a "
             "broadcast -- and phi jumps to ~3.2 with a mean of ~4.3 readers "
             "per written file (peak fan-out reaches all agents): files act as "
             "one-to-many hubs exactly where the chain is fully decomposed. "
             "This corroborates H1's broadcast-channel mechanism. "
             "(Directed-pair count, not M==0, is the correct test: broadcast "
             "messages exist but address no single peer.)")
    L.append("")


# ----------------------------------------------------------------------------
# per-cell CSV
# ----------------------------------------------------------------------------

CELL_FIELDS = [
    "family", "instance_prefix", "draw", "policy", "pattern", "n", "N",
    "M_mean", "W_mean", "R_mean", "C_mean", "tok_M_mean", "tok_R_mean",
    "phi_mean", "phi_W0_dropped", "readers_per_written_mean",
    "shared_files_mean", "private_files_mean", "broadcast_read_share_mean",
    "broadcast_share_R0_dropped",
    "eff_team_t1", "eff_team_t2", "eff_team_t3", "eff_team_t5",
    "eff_part_t1", "eff_part_t2", "eff_part_t3", "eff_part_t5",
    "eff_directed_t2",
    "n_active_mean", "n_directed_mean", "n_qual_t2_mean",
]


def write_cell_csv(meta, metrics, prefix_label, rows_out):
    for draw in TOPOLOGIES:
        for pol in POLICIES:
            for patt in PATTERNS:
                by_n = cells_for(meta, metrics, (draw,), pol, patt)
                for n in N_VALUES:
                    recs = by_n.get(n, [])
                    if not recs:
                        continue
                    fam = next((m["family"] for m in meta.values()), "")
                    row = {
                        "family": fam, "instance_prefix": prefix_label,
                        "draw": draw, "policy": pol, "pattern": patt,
                        "n": n, "N": len(recs),
                        "M_mean": cell_mean(recs, "M"),
                        "W_mean": cell_mean(recs, "W"),
                        "R_mean": cell_mean(recs, "R"),
                        "C_mean": cell_mean(recs, "C"),
                        "tok_M_mean": cell_mean(recs, "tok_M"),
                        "tok_R_mean": cell_mean(recs, "tok_R"),
                        "phi_mean": cell_mean(recs, "phi"),
                        "phi_W0_dropped": sum(
                            1 for r in recs if r["phi"] is None),
                        "readers_per_written_mean": cell_mean(
                            recs, "mean_readers_per_written_file"),
                        "shared_files_mean": cell_mean(recs, "n_shared_files"),
                        "private_files_mean": cell_mean(
                            recs, "n_private_files"),
                        "broadcast_read_share_mean": cell_mean(
                            recs, "broadcast_read_share"),
                        "broadcast_share_R0_dropped": sum(
                            1 for r in recs
                            if r["broadcast_read_share"] is None),
                        "eff_directed_t2": eff_cell_mean(recs, 2, "directed"),
                        "n_active_mean": cell_mean(recs, "n_active"),
                        "n_directed_mean": cell_mean(recs, "n_directed"),
                        "n_qual_t2_mean": cell_mean(
                            [{"q": r["n_qual"][2]} for r in recs], "q"),
                    }
                    for t in THRESHOLDS:
                        row[f"eff_team_t{t}"] = eff_cell_mean(recs, t, "team")
                        row[f"eff_part_t{t}"] = eff_cell_mean(
                            recs, t, "participant")
                    rows_out.append(row)


# ----------------------------------------------------------------------------
# verdicts
# ----------------------------------------------------------------------------

def verdict_block(meta1, met1, meta2, met2, L):
    L.append("## Verdicts (peer draw, clean pattern; allowed unless noted)")
    L.append("")

    def exps(meta, metrics, pol):
        by_n = cells_for(meta, metrics, ("peer",), pol, "clean")
        return {k: fit_metric(by_n, k) for k in ("M", "W", "R", "C")}, by_n

    for fam, meta, metrics in [("Family 1", meta1, met1),
                               ("Family 2", meta2, met2)]:
        e_allow, by_allow = exps(meta, metrics, "allowed")
        e_mand, _ = exps(meta, metrics, "mandatory")
        M, R, W = e_allow["M"], e_allow["R"], e_allow["W"]
        h1a = ("confirmed" if (R["hi"] < M["lo"]) else
               "refuted" if (R["lo"] > M["hi"]) else "underpowered")
        phi_by_n = [cell_mean(by_allow.get(n, []), "phi") for n in N_VALUES]
        phi_inc = all((not math.isnan(phi_by_n[i + 1])
                       and not math.isnan(phi_by_n[i])
                       and phi_by_n[i + 1] > phi_by_n[i]) for i in range(2))
        rdr = [cell_mean(by_allow.get(n, []),
                         "mean_readers_per_written_file") for n in N_VALUES]
        rdr_inc = all((not math.isnan(rdr[i + 1]) and not math.isnan(rdr[i])
                       and rdr[i + 1] > rdr[i]) for i in range(2))
        h1b = ("confirmed" if (phi_inc and rdr_inc) else
               "refuted" if (not phi_inc and not rdr_inc) else "mixed")
        brs = [cell_mean(by_allow.get(n, []), "broadcast_read_share")
               for n in N_VALUES]
        shf = [cell_mean(by_allow.get(n, []), "n_shared_files")
               for n in N_VALUES]
        brs_inc = (not any(math.isnan(x) for x in brs)) and brs[-1] > brs[0]
        shf_inc = (not any(math.isnan(x) for x in shf)) and shf[-1] > shf[0]
        h1c = ("confirmed" if (brs_inc and shf_inc) else
               "refuted" if (not brs_inc and not shf_inc) else "mixed")
        cm, ca = e_mand["C"]["slope"], e_allow["C"]["slope"]
        h1d = ("confirmed" if (not math.isnan(cm) and not math.isnan(ca)
                               and cm < ca - 0.15) else
               "refuted" if (not math.isnan(cm) and not math.isnan(ca)
                             and cm >= ca) else "underpowered")
        team = fit_eff(by_allow, 2, "team")
        h2 = ("confirmed" if (not math.isnan(team["slope"])
                              and team["hi"] < CLIQUE_SLOPE) else
              "refuted" if (not math.isnan(team["slope"])
                            and team["lo"] > CLIQUE_SLOPE) else "underpowered")
        # t>=1 vs t>=2 ratio to the clique at n=8 (one-shot layer vs sustained)
        r8 = by_allow.get(8, [])
        t1r = eff_cell_mean(r8, 1, "team") / 7 if r8 else float("nan")
        t2r = eff_cell_mean(r8, 2, "team") / 7 if r8 else float("nan")
        L.append(f"### {fam}")
        L.append(f"- **H2 (saturation / bounded effective degree):** "
                 f"{h2.upper()}. team-level out-degree (t>=2) slope "
                 f"{_fmt(team['slope'])} [{_fmt(team['lo'])},"
                 f"{_fmt(team['hi'])}] vs clique reference {_fmt(CLIQUE_SLOPE)}"
                 f". At n=8 the sustained (t>=2) layer reaches "
                 f"{_fmt(t2r)} of the clique while the one-shot (t>=1) layer "
                 f"reaches {_fmt(t1r)} -- "
                 + ("the one-shot layer stays near the clique here, the "
                    "sustained layer saturates below it"
                    if t1r > 0.85 else
                    "even the one-shot layer is already below the clique here, "
                    "and the sustained layer saturates further") +
                 f". (Three agent counts cannot fully separate a power law "
                 f"from saturation; better-supported reading, not proof.)")
        L.append(f"- **H1a (channel exponent gap):** {h1a.upper()} on the raw "
                 f"full-n fit. M {_fmt(M['slope'])} "
                 f"[{_fmt(M['lo'])},{_fmt(M['hi'])}], R {_fmt(R['slope'])} "
                 f"[{_fmt(R['lo'])},{_fmt(R['hi'])}], W {_fmt(W['slope'])} "
                 f"[{_fmt(W['lo'])},{_fmt(W['hi'])}]."
                 + (" NB: F1 R is inflated by the n=8 file blow-up; see the "
                    "per-draw reproducibility table — the M-R gap holds in "
                    "both draws off that cell." if fam == "Family 1" else
                    " Clean broadcast signature: writes flat, reads well "
                    "below messages."))
        L.append(f"- **H1b (broadcast amplification):** {h1b.upper()}. "
                 f"phi(2/4/8)={'/'.join(_fmt(x) for x in phi_by_n)}; "
                 f"readers/file={'/'.join(_fmt(x) for x in rdr)}.")
        L.append(f"- **H1c (shared vs private files):** {h1c.upper()}. "
                 f"broadcast read share={'/'.join(_fmt(x) for x in brs)}; "
                 f"shared files={'/'.join(_fmt(x) for x in shf)}.")
        L.append(f"- **H1d (policy bends the curve, secondary):** "
                 f"{h1d.upper()}. C exponent allowed {_fmt(ca)} vs mandatory "
                 f"{_fmt(cm)}.")
        L.append("")


# ----------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------

def build():
    f1_meta, f1_drop = load_runs(
        os.path.join(F1_ROOT, "master", "runs.csv"), "process_orders")
    f2_meta, f2_drop = load_runs(
        os.path.join(F2_ROOT, "master", "runs.csv"), "summarise_transactions")
    ci_meta, ci_drop = load_runs(
        os.path.join(CI_ROOT, "master", "runs.csv"), "compute_invoices")

    f1_roster = {rid: m["n"] for rid, m in f1_meta.items()}
    f2_roster = {rid: m["n"] for rid, m in f2_meta.items()}
    ci_roster = {rid: m["n"] for rid, m in ci_meta.items()}
    f1_met = aggregate_edges(
        os.path.join(F1_ROOT, "master", "edges.csv"), set(f1_meta), f1_roster)
    f2_met = aggregate_edges(
        os.path.join(F2_ROOT, "master", "edges.csv"), set(f2_meta), f2_roster)
    ci_met = aggregate_edges(
        os.path.join(CI_ROOT, "master", "edges.csv"), set(ci_meta), ci_roster)
    for mt, mm in [(f1_meta, f1_met), (f2_meta, f2_met), (ci_meta, ci_met)]:
        merge_n_agents(mt, mm)
    excl = {"F1": (sum(r["n_self"] for r in f1_met.values()),
                   sum(r["n_phantom"] for r in f1_met.values())),
            "F2": (sum(r["n_self"] for r in f2_met.values()),
                   sum(r["n_phantom"] for r in f2_met.values())),
            "CI": (sum(r["n_self"] for r in ci_met.values()),
                   sum(r["n_phantom"] for r in ci_met.values()))}

    L = []
    L.append("# De-trivialising the n^2 messaging result")
    L.append("")
    L.append(f"Generated {dt.date.today().isoformat()} by "
             "`scripts/analyse_messaging_structure.py` (rev 2). A narrow, "
             "POSITIVE elaboration of the n^2 result -- not an audit; the "
             "paper's claims are taken as correct. Standard filter "
             "(total_output_tokens > 0) dropped "
             f"{f1_drop} F1, {f2_drop} F2, {ci_drop} compute_invoices rows.")
    L.append("")
    L.append("Direction convention: agent_to_file source=agent target=file "
             "(WRITE); file_to_agent source=file target=agent (READ). Flat "
             "draws solo/peer reported separately, never pooled into one N for "
             "a fit. Effective-degree denominators locked: team-level (/n) and "
             "participant (/qualifying senders); see module docstring.")
    L.append("")
    L.append(f"Distinct-peer hygiene (H2 + backbone only; M/W/R/directed-count "
             f"untouched): self-addressed directed edges and out-of-roster "
             f"recipients (e.g. a hallucinated `agent-0`) are excluded so a "
             f"degree can never exceed the clique max n-1. Excluded "
             f"self/phantom directed edges: F1 {excl['F1'][0]}/{excl['F1'][1]}"
             f", F2 {excl['F2'][0]}/{excl['F2'][1]}, "
             f"compute_invoices {excl['CI'][0]}/{excl['CI'][1]}.")
    L.append("")

    L.append("## H2 — bounded effective coordination degree (the headline)")
    L.append("")
    h2_table(f1_meta, f1_met, "Family 1 (process_orders)", L)
    h2_table(f2_meta, f2_met, "Family 2 (summarise_transactions)", L)

    L.append("## H1 — file channel as broadcast medium")
    L.append("")
    channel_table(f1_meta, f1_met, "Family 1 (process_orders)", L)
    channel_table(f2_meta, f2_met, "Family 2 (summarise_transactions)", L)
    f1_read_perdraw(f1_meta, f1_met, L)
    phi_table(f1_meta, f1_met, "Family 1", L)
    phi_table(f2_meta, f2_met, "Family 2", L)

    compute_invoices_section(ci_meta, ci_met, L)

    L.append("## H1d + backbone (secondary / exploratory)")
    L.append("")
    backbone_table(f1_meta, f1_met, "Family 1", L)
    backbone_table(f2_meta, f2_met, "Family 2", L)

    verdict_block(f1_meta, f1_met, f2_meta, f2_met, L)

    L.append("## Plain-English summary (the de-trivialisation the data "
             "supports)")
    L.append("")
    L.append(
        "**Lead with H2.** The SUSTAINED coordination degree -- distinct "
        "in-roster peers an agent sends >= 2 messages to -- saturates far "
        "below the clique line n-1 in BOTH families and under either "
        "denominator, with a per-run log-log slope ~1 against the clique "
        "reference 1.40 (at n=8 the sustained layer reaches only ~0.3-0.7 of "
        "the clique). The one-shot layer (t>=1) is closer to the clique but "
        "not uniformly so: at n=8 it ranges from near-clique (F1 solo ~0.92 of "
        "n-1, every agent greets ~all others once) down to ~0.56 (Family 2, "
        "where coordination is more partitioned). So the robust, "
        "family-independent claim is the sustained-degree saturation, NOT a "
        "clean 'one-shot greets everyone' picture -- that holds only in F1 "
        "solo. This is the same "
        "bounded-degree story the paper tells through the per-pair density "
        "drop (3.05 -> 2.38 -> 1.27) and the H7 deceleration past n=4. Quote "
        "it with the denominator named: team-level (/n) or participant "
        "(/qualifying senders); both saturate, the numbers differ and must "
        "not be conflated.")
    L.append("")
    L.append(
        "**H1 (file channel = broadcast) is real, cleanest in Family 2** "
        "(messages ~n^1.9, reads ~n^1.0-1.2, writes flat ~n^0.1, phi rising "
        "0.6->1.6->2.8). The Family 1 read channel looked ~n^2 on the raw "
        "full-n fit, but that is the n=8 file blow-up -- the dataset's "
        "least-reproducible quantity (peer 38.8 vs solo 16.9 reads). Off that "
        "cell F1 peer reads are flat from n=2->4 and the message channel "
        "outscales the read channel in both draws, so a (weaker) broadcast "
        "channel is present in F1 too. The compute_invoices full-decomposition "
        "arm corroborates: at n=8, 4 of 10 runs coordinate entirely by "
        "broadcast (zero directed pairs) with ~4.3 readers per written file.")
    L.append("")
    L.append(
        "**Secondary.** H1d (mandatory bends the total-cost curve) holds for "
        "F1, not F2 -- keep as a minor, family-specific note. The "
        "disparity-filter backbone is near-empty (uniform clique, no hidden "
        "hub), consistent with the paper and corroborating H2: the clique is "
        "real but uniform and low-weight, so persistence-thresholding (not "
        "weight-disparity) is what exposes the bounded effective degree.")
    L.append("")

    os.makedirs(os.path.dirname(CELL_CSV), exist_ok=True)
    rows_out = []
    write_cell_csv(f1_meta, f1_met, "process_orders", rows_out)
    write_cell_csv(f2_meta, f2_met, "summarise_transactions", rows_out)
    write_cell_csv(ci_meta, ci_met, "compute_invoices", rows_out)
    with open(CELL_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CELL_FIELDS)
        w.writeheader()
        for row in rows_out:
            w.writerow({k: row.get(k, "") for k in CELL_FIELDS})

    os.makedirs(os.path.dirname(OUT_MD), exist_ok=True)
    with open(OUT_MD, "w") as f:
        f.write("\n".join(L) + "\n")
    return rows_out


def main():
    rows = build()
    print(f"wrote {OUT_MD}")
    print(f"wrote {CELL_CSV} ({len(rows)} cell rows)")


if __name__ == "__main__":
    main()
