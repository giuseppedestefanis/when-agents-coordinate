#!/usr/bin/env python3
"""RQ1 linearisation: coordination cost is channel-specific (2026-06-15).

The n^2 is a property of the one-to-one MESSAGE channel. A file write is
one-to-many (one write, many reads), so file-mediated coordination scales
sub-quadratically, and the artefact policy selects the regime. This formalises
that into committed, reproducible scaling exponents with explicit verdicts.
Reported faithfully whichever way it falls; not tuned toward "linear".

Per-run quantities (runs.csv aggregate columns, cross-checked vs edges.csv):
  M     = n_agent_to_agent              (all messages)
  M_dir = n_agent_to_agent_directed     (canonical/alias == directed)
  M_bc  = broadcast a2a edges           (edges.csv target_kind == broadcast)
  W     = n_agent_to_file               (writes)
  R     = n_file_to_agent               (reads)
  C     = M + W + R                      (total coordination edges)
  token_cost-weighted analogues per channel (sum of per-edge token_cost).
  fan-out = mean distinct reader agents per written file.

Slopes: per-run OLS of log(metric) on log(n) over n in {2,4,8} with 95% CI
(the estimator shared with analyse_handshake_timing / messaging-structure; the
slope is invariant to log base, so this equals the log2-on-log2 slope). Also
the n=2->4 segment exponent (idleness-free: all agents hold work at n<=4) and
n=4->8 segment, from cell means.

Scope: F1 process_orders/clean, F2 summarise_transactions/clean (solo & peer
separate, allowed + mandatory + forbidden); no-idleness arm
data/compute-invoices-scaling (compute_invoices/clean, peer, allowed only).
Filter total_output_tokens>0, n in {2,4,8}. Never pool draws.

Usage:
    .venv/bin/python scripts/analyse_channel_scaling.py
"""

from __future__ import annotations

import csv
import datetime as dt
import math
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from analyse_solo_peer_reliability import linregress_slope_ci

csv.field_size_limit(10 ** 7)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
F1_ROOT = os.path.join(REPO, "data", "family-1-full")
F2_ROOT = os.path.join(REPO, "data", "family-2-full")
CI_ROOT = os.path.join(REPO, "data", "compute-invoices-scaling")

OUT_MD = os.path.join(REPO, "memory", "experiments", "channel-scaling.md")
CELL_CSV = os.path.join(REPO, "data", "derived", "channel-scaling-cells.csv")

N_VALUES = (2, 4, 8)
FLAT_DRAWS = ("solo", "peer")
POLICIES = ("forbidden", "allowed", "mandatory")
# the channel metrics we fit
METRICS = ("M", "M_dir", "M_bc", "W", "R", "C",
           "tok_M", "tok_W", "tok_R", "tok_C")


def load_runs(runs_csv, instance):
    """{run_id: meta+counts} for total_output_tokens>0 rows of one instance."""
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
            if n not in N_VALUES:
                continue
            meta[r["run_id"]] = {
                "n": n, "topology": r["topology"],
                "policy": r["artefact_policy"],
                "M": float(r["n_agent_to_agent"]),
                "M_dir": float(r["n_agent_to_agent_directed"]),
                "W": float(r["n_agent_to_file"]),
                "R": float(r["n_file_to_agent"]),
            }
    return meta, dropped


def aggregate_edges(edges_csv, valid):
    """Per run: M_bc (broadcast count), token_cost per channel, fan-out, and
    a cross-check of directed (canonical+alias) edge count."""
    bc = Counter()
    tok = defaultdict(lambda: {"M": 0.0, "W": 0.0, "R": 0.0})
    writes_readers = defaultdict(lambda: defaultdict(set))   # file -> readers
    written = defaultdict(set)                               # files written
    dir_edges = Counter()                                    # cross-check
    a2a = Counter()
    with open(edges_csv, newline="") as f:
        for r in csv.DictReader(f):
            rid = r["run_id"]
            if rid not in valid:
                continue
            et = r["edge_type"]
            t = float(r["token_cost"]) if r["token_cost"].strip() else 0.0
            if et == "agent_to_agent":
                a2a[rid] += 1
                tok[rid]["M"] += t
                k = r["target_kind"]
                if k == "broadcast":
                    bc[rid] += 1
                elif k in ("canonical", "alias"):
                    dir_edges[rid] += 1
            elif et == "agent_to_file":
                tok[rid]["W"] += t
                written[rid].add(r["target"])
            elif et == "file_to_agent":
                tok[rid]["R"] += t
                writes_readers[rid][r["source"]].add(r["target"])
    out = {}
    for rid in valid:
        wf = written.get(rid, set())
        readers = writes_readers.get(rid, {})
        fan = ([len(readers.get(fp, set())) for fp in wf] if wf else [])
        out[rid] = {
            "M_bc": bc.get(rid, 0),
            "tok_M": tok[rid]["M"], "tok_W": tok[rid]["W"],
            "tok_R": tok[rid]["R"],
            "mean_readers_per_written_file": (sum(fan) / len(fan)
                                              if fan else None),
            "dir_edges": dir_edges.get(rid, 0),
        }
    return out


def build_records(meta, edge_metrics):
    """Merge runs.csv counts with edge-derived metrics into per-run records."""
    recs = {}
    for rid, m in meta.items():
        e = edge_metrics[rid]
        recs[rid] = {
            "n": m["n"], "topology": m["topology"], "policy": m["policy"],
            "M": m["M"], "M_dir": m["M_dir"], "M_bc": e["M_bc"],
            "W": m["W"], "R": m["R"], "C": m["M"] + m["W"] + m["R"],
            "tok_M": e["tok_M"], "tok_W": e["tok_W"], "tok_R": e["tok_R"],
            "tok_C": e["tok_M"] + e["tok_W"] + e["tok_R"],
            "mean_readers_per_written_file":
                e["mean_readers_per_written_file"],
            "_dir_edges": e["dir_edges"], "_M_dir_col": m["M_dir"],
        }
    return recs


def cell(recs, draw, policy, n):
    return [r for r in recs.values() if r["topology"] == draw
            and r["policy"] == policy and r["n"] == n]


def cmean(rows, key):
    vs = [r[key] for r in rows if r.get(key) is not None]
    return (sum(vs) / len(vs)) if vs else float("nan")


def fit(recs, draw, policy, key):
    """Per-run OLS log-log slope+CI; plus cell means and segment exponents."""
    xs, ys, means = [], [], {}
    for n in N_VALUES:
        vals = [r[key] for r in cell(recs, draw, policy, n)
                if r.get(key) is not None and r[key] > 0]
        for v in vals:
            xs.append(math.log(n))
            ys.append(math.log(v))
        means[n] = (sum(vals) / len(vals)) if vals else None
    b, lo, hi = linregress_slope_ci(xs, ys)
    seg24 = (math.log2(means[4] / means[2])
             if means.get(2) and means.get(4) else float("nan"))
    seg48 = (math.log2(means[8] / means[4])
             if means.get(4) and means.get(8) else float("nan"))
    return {"slope": b, "lo": lo, "hi": hi, "means": means,
            "seg24": seg24, "seg48": seg48, "npts": len(xs)}


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

def _f(x, p=2):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "--"
    return f"{x:.{p}f}"


def exponents_table(recs, fam_label, L):
    L.append(f"#### {fam_label} — channel scaling exponents (per-run log-log "
             f"slope [95% CI]; seg = cell-mean segment exponent)")
    L.append("")
    for pol in POLICIES:
        L.append(f"*Policy: {pol}*")
        L.append("")
        L.append("| draw / channel | slope [95% CI] | seg 2->4 | seg 4->8 | "
                 "n=2/4/8 means |")
        L.append("|---|---|---:|---:|---|")
        for draw in FLAT_DRAWS:
            if not cell(recs, draw, pol, 2):
                continue
            for key in ("M_dir", "M_bc", "W", "R", "C", "tok_C"):
                fr = fit(recs, draw, pol, key)
                mn = "/".join(_f(fr["means"].get(n), 1) for n in N_VALUES)
                L.append(f"| {draw} / {key} | {_f(fr['slope'])} "
                         f"[{_f(fr['lo'])}, {_f(fr['hi'])}] | "
                         f"{_f(fr['seg24'])} | {_f(fr['seg48'])} | {mn} |")
        L.append("")


def fanout_table(recs, fam_label, L):
    L.append(f"#### {fam_label} — readers per written file (peer)")
    L.append("")
    L.append("| policy | n=2 | n=4 | n=8 |")
    L.append("|---|---:|---:|---:|")
    for pol in POLICIES:
        vals = [_f(cmean(cell(recs, "peer", pol, n),
                          "mean_readers_per_written_file"))
                for n in N_VALUES]
        if all(v == "--" for v in vals):
            continue
        L.append(f"| {pol} | " + " | ".join(vals) + " |")
    L.append("")


CELL_FIELDS = ["family", "draw", "policy", "n", "N",
               "M_mean", "M_dir_mean", "M_bc_mean", "W_mean", "R_mean",
               "C_mean", "tok_C_mean", "readers_per_written_mean",
               "C_slope", "C_lo", "C_hi", "C_seg24",
               "M_dir_slope", "W_slope", "R_slope", "tok_C_slope"]


def write_cells(recs, family, rows_out):
    for draw in FLAT_DRAWS:
        for pol in POLICIES:
            for n in N_VALUES:
                rows = cell(recs, draw, pol, n)
                if not rows:
                    continue
                cfit = fit(recs, draw, pol, "C")
                row = {
                    "family": family, "draw": draw, "policy": pol, "n": n,
                    "N": len(rows),
                    "M_mean": cmean(rows, "M"),
                    "M_dir_mean": cmean(rows, "M_dir"),
                    "M_bc_mean": cmean(rows, "M_bc"),
                    "W_mean": cmean(rows, "W"), "R_mean": cmean(rows, "R"),
                    "C_mean": cmean(rows, "C"),
                    "tok_C_mean": cmean(rows, "tok_C"),
                    "readers_per_written_mean": cmean(
                        rows, "mean_readers_per_written_file"),
                    "C_slope": cfit["slope"], "C_lo": cfit["lo"],
                    "C_hi": cfit["hi"], "C_seg24": cfit["seg24"],
                    "M_dir_slope": fit(recs, draw, pol, "M_dir")["slope"],
                    "W_slope": fit(recs, draw, pol, "W")["slope"],
                    "R_slope": fit(recs, draw, pol, "R")["slope"],
                    "tok_C_slope": fit(recs, draw, pol, "tok_C")["slope"],
                }
                rows_out.append(row)


def verdicts(f1, f2, ci, L):
    L.append("## Verdicts")
    L.append("")
    for fam, recs in [("Family 1 (process_orders, distributed)", f1),
                      ("Family 2 (summarise_transactions)", f2)]:
        L.append(f"### {fam}")
        for draw in FLAT_DRAWS:
            md = fit(recs, draw, "allowed", "M_dir")
            w = fit(recs, draw, "allowed", "W")
            r = fit(recs, draw, "allowed", "R")
            # H-channel: writes scale strictly slower than directed messages
            hc = ("confirmed" if (not math.isnan(w["hi"])
                  and not math.isnan(md["lo"]) and w["hi"] < md["lo"])
                  else "refuted" if (w["lo"] > md["hi"]) else "underpowered")
            L.append(
                f"- **H-channel ({draw}, allowed):** {hc.upper()} for writes. "
                f"M_dir {_f(md['slope'])}[{_f(md['lo'])},{_f(md['hi'])}] vs "
                f"W {_f(w['slope'])}[{_f(w['lo'])},{_f(w['hi'])}]; "
                f"R {_f(r['slope'])}[{_f(r['lo'])},{_f(r['hi'])}]"
                + (" (reads NOT sub-quadratic here -- the n=8 file blow-up; "
                   "see confound 5)" if r["lo"] > 1.5 else "") + ".")
        # H-policy-selects-regime
        for draw in FLAT_DRAWS:
            ca = fit(recs, draw, "allowed", "C")
            cm = fit(recs, draw, "mandatory", "C")
            drop = (ca["slope"] - cm["slope"]
                    if not math.isnan(ca["slope"]) else float("nan"))
            hp = ("confirmed (mandatory lowers C)" if drop > 0.15 else
                  "refuted (mandatory does not lower C)" if drop <= 0
                  else "marginal")
            L.append(
                f"- **H-policy-selects-regime ({draw}):** {hp.upper()}. "
                f"C exponent allowed {_f(ca['slope'])} -> mandatory "
                f"{_f(cm['slope'])} (drop {_f(drop)}); token-cost C "
                f"{_f(fit(recs, draw, 'allowed', 'tok_C')['slope'])} -> "
                f"{_f(fit(recs, draw, 'mandatory', 'tok_C')['slope'])}.")
        # H-broadcast
        for draw in ("peer",):
            rd = [cmean(cell(recs, draw, "allowed", n),
                        "mean_readers_per_written_file") for n in N_VALUES]
            hb = ("confirmed" if (not any(math.isnan(x) for x in rd)
                  and rd[-1] > rd[0] and rd[-1] > 1) else "mixed")
            L.append(f"- **H-broadcast ({draw}, allowed):** {hb.upper()}. "
                     f"readers/written file n=2/4/8 = "
                     f"{'/'.join(_f(x) for x in rd)}.")
        # confound 5: F1 mandatory read channel still super-linear
        if "process_orders" in fam:
            rm = fit(recs, "peer", "mandatory", "R")
            L.append(f"- **Confound 5 (F1-mandatory honesty):** the file-READ "
                     f"channel under mandatory is still super-linear "
                     f"(R slope {_f(rm['slope'])}"
                     f"[{_f(rm['lo'])},{_f(rm['hi'])}]); C is near-linear "
                     f"because directed messaging is switched off (M_dir "
                     f"mandatory peer slope "
                     f"{_f(fit(recs, 'peer', 'mandatory', 'M_dir')['slope'])})"
                     f" and the n=2 baseline is high -- NOT because the F1 file "
                     f"channel is intrinsically linear.")
        L.append("")
    # no-idleness reference
    ca = fit(ci, "peer", "allowed", "C")
    md = fit(ci, "peer", "allowed", "M_dir")
    w = fit(ci, "peer", "allowed", "W")
    r = fit(ci, "peer", "allowed", "R")
    L.append("### No-idleness arm (compute_invoices/clean, peer, allowed "
             "only)")
    L.append(f"- **Confound 1 (idleness reference):** at full decomposition "
             f"(n=8 has no idle agents) the allowed total-C exponent is "
             f"{_f(ca['slope'])}[{_f(ca['lo'])},{_f(ca['hi'])}] "
             f"(seg 2->4 {_f(ca['seg24'])}, 4->8 {_f(ca['seg48'])}); "
             f"M_dir {_f(md['slope'])}, W {_f(w['slope'])}, R {_f(r['slope'])}. "
             f"Allowed-only, so the mandatory linearisation cannot be tested "
             f"idleness-free here.")
    L.append("")


def build():
    f1m, f1d = load_runs(os.path.join(F1_ROOT, "master", "runs.csv"),
                         "process_orders/clean")
    f2m, f2d = load_runs(os.path.join(F2_ROOT, "master", "runs.csv"),
                         "summarise_transactions/clean")
    cim, cid = load_runs(os.path.join(CI_ROOT, "master", "runs.csv"),
                         "compute_invoices/clean")
    f1e = aggregate_edges(os.path.join(F1_ROOT, "master", "edges.csv"),
                          set(f1m))
    f2e = aggregate_edges(os.path.join(F2_ROOT, "master", "edges.csv"),
                          set(f2m))
    cie = aggregate_edges(os.path.join(CI_ROOT, "master", "edges.csv"),
                          set(cim))
    f1, f2, ci = (build_records(f1m, f1e), build_records(f2m, f2e),
                  build_records(cim, cie))

    # cross-check: directed edge count (edges) == M_dir column (runs.csv)
    mism = sum(1 for rid in f1m
               if f1[rid]["_dir_edges"] != int(f1[rid]["_M_dir_col"])) \
        + sum(1 for rid in f2m
              if f2[rid]["_dir_edges"] != int(f2[rid]["_M_dir_col"])) \
        + sum(1 for rid in cim
              if ci[rid]["_dir_edges"] != int(ci[rid]["_M_dir_col"]))

    L = []
    L.append("# RQ1 linearisation — coordination cost is channel-specific")
    L.append("")
    L.append(f"Generated {dt.date.today().isoformat()} by "
             "`scripts/analyse_channel_scaling.py`. Per-run OLS log-log slope "
             "(invariant to log base) over n in {2,4,8}; never pooling draws. "
             f"total_output_tokens>0 dropped {f1d} F1, {f2d} F2, {cid} CI. "
             f"Cross-check: directed edge count (edges.csv canonical+alias) == "
             f"n_agent_to_agent_directed column, mismatches = {mism}.")
    L.append("")
    L.append("DISCREPANCY flagged for the writer: the brief cited F1 solo "
             "allowed C exponent = 2.35; the reproducible value here is 2.11 "
             "(per-run OLS) / 2.10 (cell-mean). 2.35 is the F1 ORCHESTRATOR "
             "M-slope from the messaging-structure note -- likely a mix-up. "
             "The allowed->mandatory DROP (the headline) holds either way.")
    L.append("")

    L.append("## Channel exponents")
    L.append("")
    exponents_table(f1, "Family 1 (process_orders)", L)
    exponents_table(f2, "Family 2 (summarise_transactions)", L)
    L.append("#### compute_invoices/clean (peer, allowed; no idleness at n=8)")
    L.append("")
    L.append("| channel | slope [95% CI] | seg 2->4 | seg 4->8 | means |")
    L.append("|---|---|---:|---:|---|")
    for key in ("M_dir", "M_bc", "W", "R", "C", "tok_C"):
        fr = fit(ci, "peer", "allowed", key)
        mn = "/".join(_f(fr["means"].get(n), 1) for n in N_VALUES)
        L.append(f"| {key} | {_f(fr['slope'])} [{_f(fr['lo'])}, "
                 f"{_f(fr['hi'])}] | {_f(fr['seg24'])} | {_f(fr['seg48'])} | "
                 f"{mn} |")
    L.append("")

    L.append("## Readers per written file (broadcast fan-out)")
    L.append("")
    fanout_table(f1, "Family 1", L)
    fanout_table(f2, "Family 2", L)

    verdicts(f1, f2, ci, L)

    L.append("## Plain-English summary")
    L.append("")
    L.append(
        "The n^2 is the cost of the one-to-one DIRECTED message channel: "
        "M_dir scales near-quadratically while file WRITES scale "
        "sub-quadratically (one write serves many reads), so the artefact "
        "policy selects the regime. On the distributed task (Family 1) "
        "mandating files roughly halves the total coordination-edge exponent "
        "versus allowed (peer 1.70->1.12, solo 2.11->1.32), and the token-cost "
        "version agrees -- consistent with the ~42% mandatory token reduction "
        "at n=8. The contrast holds idleness fixed (both cells have 4 idle "
        "agents at n=8), so the policy-driven DROP is the robust claim; the "
        "absolute level is not (the no-idleness compute_invoices arm shows the "
        "allowed exponent without idle agents). Family 2 does NOT show the "
        "linearisation (mandatory C >= allowed), so 'policy selects the "
        "regime' is task-dependent, not universal. Honesty: under F1 mandatory "
        "the file-READ channel is itself still super-linear (~1.7); C is "
        "near-linear because directed messaging is switched off, not because "
        "F1's file channel is intrinsically linear -- only the chained task's "
        "is. Keep the channel contrast as the robust core; treat the "
        "'near-linear' absolute level as task- and idleness-dependent.")
    L.append("")

    os.makedirs(os.path.dirname(CELL_CSV), exist_ok=True)
    rows_out = []
    write_cells(f1, "process_orders", rows_out)
    write_cells(f2, "summarise_transactions", rows_out)
    write_cells(ci, "compute_invoices", rows_out)
    with open(CELL_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CELL_FIELDS)
        w.writeheader()
        for row in rows_out:
            w.writerow({k: row.get(k, "") for k in CELL_FIELDS})

    os.makedirs(os.path.dirname(OUT_MD), exist_ok=True)
    with open(OUT_MD, "w") as f:
        f.write("\n".join(L) + "\n")
    return rows_out, mism


def main():
    rows, mism = build()
    print(f"wrote {OUT_MD}")
    print(f"wrote {CELL_CSV} ({len(rows)} cell rows); dir cross-check "
          f"mismatches={mism}")


if __name__ == "__main__":
    main()
