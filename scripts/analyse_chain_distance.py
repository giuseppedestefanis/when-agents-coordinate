#!/usr/bin/env python3
"""Review issue 6: chain-distance distribution of directed agent-to-agent
messages in the Family-2 sequential-dependency tasks.

Tests the §5.1 "negotiations with every agent ahead" / all-upstream claim. For
each ordered directed message (sender -> recipient agent), the chain distance
is |step(sender) - step(recipient)|, where each agent's pipeline step is read
from the run's instance.json (full decomposition: one step per agent). The
mechanism behind the all-upstream reading predicts non-trivial mass at
distance >= 2; the rival (linear pipeline) reading predicts mass decaying to
~0 beyond adjacent (distance 1).

Attribution policy (stated, per the brief):
  * canonical / alias targets -> the named agent's step (direct).
  * role targets (a function name, e.g. "compute_tax") -> the step whose
    instance.json label is that function; mapped to the agent holding it.
  * broadcast targets ("*") -> counted SEPARATELY and reported as a share, NOT
    given a distance and NOT spread to all agents: a broadcast has no single
    recipient, and spreading it would fabricate a distance distribution. The
    directed distance distribution is the test; the broadcast share is the
    caveat on its coverage.
  * unknown / unresolved targets -> reported as a separate count, excluded.

Substrates:
  * compute_invoices n=8 (8 chain steps, full decomposition, peer/allowed/clean,
    single session) -- the cleanest test.
  * summarise_transactions n=4 (peer) -- the Family-2-proper reading.

Data dependency: this script reads the per-run directories (instance.json for
the agent->step map, datasets/edges.csv for the typed edges), NOT the master
CSVs -- the step map is per-run and not carried in master/. The per-run
directories ship in the released data tarball (they are git-ignored; see
data/README.md "Packaging the released artefact"), exactly like
count_workspace_files.py. A git-only checkout without the tarball has no per-run
directories, so the script reports that loudly rather than emitting an empty
result.

Usage:
    .venv/bin/python scripts/analyse_chain_distance.py
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import sys
from collections import Counter, defaultdict


def load_step_maps(instance_json):
    """Return (agent_step, label_step) from a run's instance.json.

    agent_step: {agent_id -> step index}. label_step: {function label -> step
    index}, with the "Step: " prefix stripped so role function-names resolve.
    """
    with open(instance_json) as f:
        inst = json.load(f)
    agent_step, label_step = {}, {}
    for a in inst.get("agents", []):
        comps = a.get("components", [])
        if not comps:
            continue
        # full decomposition: one component (step) per agent
        idx = comps[0]["index"]
        agent_step[a["agent_id"]] = idx
        for c in comps:
            label = c.get("label", "")
            name = label.split("Step:", 1)[1].strip() if "Step:" in label \
                else label.strip()
            if name:
                label_step[name] = c["index"]
    return agent_step, label_step


def run_distances(run_dir):
    """Yield resolved-recipient outcomes for one run's a2a edges.

    Returns a dict with: distance Counter (directed pairs), signed Counter
    (recipient_step - sender_step), and broadcast / role / unresolved counts.
    """
    inst = os.path.join(run_dir, "instance", "instance.json")
    edges_csv = os.path.join(run_dir, "datasets", "edges.csv")
    if not (os.path.exists(inst) and os.path.exists(edges_csv)):
        return None
    agent_step, label_step = load_step_maps(inst)
    dist = Counter()
    signed = Counter()
    broadcast = role_resolved = unresolved = directed = 0
    with open(edges_csv, newline="") as f:
        for e in csv.DictReader(f):
            if e["edge_type"] != "agent_to_agent":
                continue
            src = e["source"]
            if src not in agent_step:
                unresolved += 1
                continue
            s = agent_step[src]
            kind = e.get("target_kind", "")
            tgt = e["target"]
            if kind == "broadcast" or tgt == "*":
                broadcast += 1
                continue
            if kind in ("canonical", "alias") and tgt in agent_step:
                r = agent_step[tgt]
            elif kind == "role" and tgt in label_step:
                r = label_step[tgt]
                role_resolved += 1
            elif tgt in agent_step:        # any other kind naming an agent
                r = agent_step[tgt]
            else:
                unresolved += 1
                continue
            if r == s:                     # self-reference, no distance
                unresolved += 1
                continue
            dist[abs(s - r)] += 1
            signed[r - s] += 1
            directed += 1
    return {"dist": dist, "signed": signed, "broadcast": broadcast,
            "role_resolved": role_resolved, "unresolved": unresolved,
            "directed": directed}


def chain_distance(run_glob, label, lines):
    runs = sorted(glob.glob(run_glob))
    total = {"dist": Counter(), "signed": Counter(), "broadcast": 0,
             "role_resolved": 0, "unresolved": 0, "directed": 0, "n_runs": 0}
    for d in runs:
        out = run_distances(d)
        if out is None:
            continue
        total["n_runs"] += 1
        total["dist"] += out["dist"]
        total["signed"] += out["signed"]
        for k in ("broadcast", "role_resolved", "unresolved", "directed"):
            total[k] += out[k]

    directed = total["directed"]
    a2a_total = directed + total["broadcast"] + total["unresolved"]
    lines.append(f"### {label}")
    lines.append("")
    if total["n_runs"] == 0:
        lines.append(f"- **no per-run directories matched** `{run_glob}`. This "
                     "analysis needs the per-run directories (instance.json + "
                     "datasets/edges.csv), which ship in the released data "
                     "tarball, not in git. Extract the tarball under data/ and "
                     "re-run.")
        lines.append("")
        return total
    lines.append(f"- runs: {total['n_runs']}; a2a edges: {a2a_total} "
                 f"(directed pairs {directed}, broadcast {total['broadcast']} "
                 f"= {100*total['broadcast']/a2a_total:.0f}%, "
                 f"unresolved/self {total['unresolved']}); "
                 f"role-resolved among directed: {total['role_resolved']}")
    lines.append("")
    if directed == 0:
        lines.append("- no directed pairs to distribute.")
        lines.append("")
        return total
    lines.append("- directed-pair chain-distance distribution "
                 "(|step(sender) - step(recipient)|):")
    lines.append("")
    lines.append("| distance | count | % of directed |")
    lines.append("|---:|---:|---:|")
    maxd = max(total["dist"])
    adj = total["dist"].get(1, 0)
    far = sum(c for d, c in total["dist"].items() if d >= 2)
    for d in range(1, maxd + 1):
        c = total["dist"].get(d, 0)
        lines.append(f"| {d} | {c} | {100*c/directed:.1f}% |")
    lines.append("")
    upstream = sum(c for k, c in total["signed"].items() if k < 0)
    downstream = sum(c for k, c in total["signed"].items() if k > 0)
    far_frac = far / directed
    up_frac = upstream / directed
    lines.append(f"- adjacent (distance 1): {adj} ({100*adj/directed:.1f}%); "
                 f"distant (>= 2): {far} ({100*far_frac:.1f}%)")
    lines.append(f"- direction: upstream (recipient earlier in chain) "
                 f"{upstream} ({100*up_frac:.1f}%); downstream "
                 f"{downstream} ({100*downstream/directed:.1f}%)")
    distance_v = ("non-trivial distant mass at distance >= 2"
                  if far_frac >= 0.20 else
                  "mass concentrated on adjacent step (decays beyond "
                  "distance 1; linear-pipeline reading)")
    direction_v = ("upstream-dominated" if up_frac >= 0.65 else
                   "downstream-dominated" if up_frac <= 0.35 else
                   "roughly balanced upstream/downstream (NOT all-upstream)")
    lines.append(f"- **verdict (distance):** {distance_v}")
    lines.append(f"- **verdict (direction):** {direction_v}")
    lines.append("")
    return total


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="memory/experiments/"
                    "review-issue-6-chain-distance.md")
    args = ap.parse_args()
    lines = ["# Review issue 6: chain-distance distribution", ""]
    lines.append("Generated by `scripts/analyse_chain_distance.py`. "
                 "Attribution: directed (canonical/alias) -> named agent's "
                 "step; role -> the step of that function name; broadcast "
                 "counted separately (not spread); unknown/self excluded.")
    lines.append("")
    t1 = chain_distance(
        "data/compute-invoices-scaling/runs/"
        "family-2-compute_invoices-clean-a8-peer-allowed-r*",
        "compute_invoices n=8 (peer/allowed/clean) — primary substrate", lines)
    t2 = chain_distance(
        "data/family-2-full/runs/"
        "family-2-summarise_transactions-*-a4-peer-*",
        "summarise_transactions n=4 (peer, all patterns/policies)", lines)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"wrote {args.out}")
    if t1["n_runs"] == 0 and t2["n_runs"] == 0:
        print("WARNING: no per-run directories found. This script needs the "
              "released data tarball (per-run instance.json + datasets/), not "
              "just the git-tracked master CSVs. See the docstring.")
    for label, t in (("compute_invoices n=8", t1),
                     ("summarise_transactions n=4", t2)):
        d = t["directed"]
        if d:
            far = sum(c for k, c in t["dist"].items() if k >= 2)
            print(f"{label}: directed={d}, adjacent={100*t['dist'].get(1,0)/d:.0f}%, "
                  f"distant>=2={100*far/d:.0f}%, broadcast={t['broadcast']}")


if __name__ == "__main__":
    main()
