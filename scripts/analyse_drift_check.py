#!/usr/bin/env python3
"""Within-cell drift check for the appendix claim that a regression of
messaging on run order shows no drift.

Construction (stated so the check is reproducible): for every full-schedule
cell with at least ten runs and at least two agents, order the cell's runs by
the timestamp of their first model turn and regress the run's
n_agent_to_agent count on that rank (ordinary least squares). The share of
cells with a raw p < 0.05 trend is compared with the 5% expected by chance;
no correction is applied because the claim is about the absence of a
systematic pattern.
"""
from pathlib import Path
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]

def main():
    sig = tot = 0
    for ds in ("family-1-full", "family-2-full"):
        r = pd.read_csv(ROOT / "data" / ds / "master" / "runs.csv",
                        usecols=["run_id", "instance", "agent_count",
                                 "topology", "artefact_policy",
                                 "n_agent_to_agent"])
        t = pd.read_csv(ROOT / "data" / ds / "master" / "turns.csv",
                        usecols=["run_id", "timestamp"])
        first = t.groupby("run_id").timestamp.min()
        r = r.assign(t0=r.run_id.map(first))
        for key, g in r.groupby(["instance", "agent_count", "topology",
                                 "artefact_policy"]):
            if len(g) < 10 or key[1] < 2 or g.n_agent_to_agent.nunique() == 1:
                continue
            g = g.sort_values("t0").reset_index(drop=True)
            tot += 1
            if stats.linregress(g.index, g.n_agent_to_agent).pvalue < 0.05:
                sig += 1
    print(f"cells with a raw-significant (p<0.05) trend of messaging on "
          f"run order: {sig}/{tot} ({100*sig/tot:.1f}%; chance rate 5%)")

if __name__ == "__main__":
    main()
