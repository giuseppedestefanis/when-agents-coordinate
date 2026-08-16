#!/usr/bin/env python3
"""Containment supporting analyses: the exclusion re-test and the dilution
comparison (containment section).

Affected run: any file-tool read whose path lies outside /workspace/.

Exclusion re-test: drop every affected run from the two full schedules and
recompute the confirmatory quantities; the paper's claim is that they
survive.

Dilution comparison: the file-policy output-token saving at eight agents on
the distributed task, in the runs with no out-of-workspace read, across all
affected runs, and across read-count tertiles of the affected runs (the
"most-affected third" is the top tertile by out-of-workspace read count).
"""
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
D = lambda ds, f: ROOT / "data" / ds / "master" / f

def affected(ds):
    e = pd.read_csv(D(ds, "edges.csv"), usecols=["run_id", "edge_type", "source"])
    rd = e[e.edge_type == "file_to_agent"]
    return set(rd[~rd.source.str.contains("/workspace/", na=False)].run_id)

def saving(sub):
    a = sub[sub.artefact_policy == "allowed"].total_output_tokens.mean()
    m = sub[sub.artefact_policy == "mandatory"].total_output_tokens.mean()
    return round(100 * (1 - m / a))

def main():
    r1 = pd.read_csv(D("family-1-full", "runs.csv"))
    r2 = pd.read_csv(D("family-2-full", "runs.csv"))
    a1, a2 = affected("family-1-full"), affected("family-2-full")
    k1, k2 = r1[~r1.run_id.isin(a1)], r2[~r2.run_id.isin(a2)]
    print(f"kept after exclusion: F1 {len(k1)}/{len(r1)}, F2 {len(k2)}/{len(r2)}")

    h1 = k2[(k2.topology.isin(["solo", "peer"])) & (k2.artefact_policy == "allowed")
            & (k2.instance == "summarise_transactions/clean")
            & (k2.agent_count >= 2) & (k2.n_agent_to_agent > 0)]
    res = stats.linregress(np.log(h1.agent_count), np.log(h1.n_agent_to_agent))
    print(f"H1 slope on kept runs: {res.slope:.2f} (all runs: 1.92)")

    n8 = k1[k1.agent_count == 8]
    print(f"output-token cut at n=8 on kept runs: {saving(n8)}% (all runs: 42%)")

    h4 = k2.groupby("artefact_policy").n_file_nodes.mean()
    print("H4 ordering on kept runs (mandatory > allowed > forbidden):",
          bool(h4["mandatory"] > h4["allowed"] > h4["forbidden"]))

    c = k1[(k1.agent_count == 8) & (k1.instance == "process_orders/conflicting")]
    for pol in ("forbidden", "allowed", "mandatory"):
        d = c[c.artefact_policy == pol]
        fl, oc = d[d.topology.isin(["solo", "peer"])], d[d.topology == "orchestrator"]
        tab = [[fl.success.sum(), len(fl) - fl.success.sum()],
               [oc.success.sum(), len(oc) - oc.success.sum()]]
        p = stats.fisher_exact(tab)[1]
        print(f"coordinator contrast on kept runs, {pol}: flat "
              f"{int(fl.success.sum())}/{len(fl)} vs coordinator "
              f"{int(oc.success.sum())}/{len(oc)}, Fisher p={p:.2f}")

    n8all = r1[r1.agent_count == 8]
    aff = n8all[n8all.run_id.isin(a1)].copy()
    clean = n8all[~n8all.run_id.isin(a1)]
    e1 = pd.read_csv(D("family-1-full", "edges.csv"), usecols=["run_id", "edge_type", "source"])
    outw = e1[(e1.edge_type == "file_to_agent")
              & ~e1.source.str.contains("/workspace/", na=False)]
    cnt = outw.groupby("run_id").size()
    aff["k"] = aff.run_id.map(cnt)
    lo_c, hi_c = np.quantile(aff.k, [1 / 3, 2 / 3])
    print(f"dilution: saving {saving(clean)}% (no out-of-workspace read), "
          f"{saving(aff)}% (all affected), tertiles "
          f"{saving(aff[aff.k <= lo_c])}/{saving(aff[(aff.k > lo_c) & (aff.k <= hi_c)])}/"
          f"{saving(aff[aff.k > hi_c])}% (most-affected third last)")

if __name__ == "__main__":
    main()
