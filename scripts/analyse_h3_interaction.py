#!/usr/bin/env python3
"""Reproduce the exploratory cross-experiment H3 interaction (p = 0.24).

The paper's H3 is pre-registered as a within-Experiment-2 Fisher test (see
`preregistration/experiment-2-analysis-plan.md`). The manuscript also reports an
*exploratory* cross-experiment test of whether the coordinator effect on the
conflicting split differs between the two experiments. This script documents and
reproduces that exploratory model, which was an ad-hoc review-response analysis
not otherwise in the released scripts.

Model: pool the n=4 conflicting cells of both experiments, flat (peer) against
orchestrator, across all three file policies; fit a logistic regression of
success on the topology-by-experiment interaction and report the interaction
p-value.

    success ~ orchestrator * experiment      (statsmodels logit)

Reads:  data/family-1-full/master/runs.csv   (Experiment 1)
        data/family-2-full/master/runs.csv   (Experiment 2)
"""
from __future__ import annotations
import warnings
from pathlib import Path

import pandas as pd
import statsmodels.formula.api as smf

ROOT = Path(__file__).resolve().parents[1]


def _cells(fam, instance):
    r = pd.read_csv(ROOT / "data" / fam / "master" / "runs.csv")
    r = r[r.run_id.str.contains(f"{instance}-conflicting-a4-")]
    r = r[r.topology.isin(["peer", "orchestrator"])].copy()
    r["success"] = r.success.astype(str).str.lower().eq("true").astype(int)
    r["orchestrator"] = (r.topology == "orchestrator").astype(int)
    return r


def main():
    e1 = _cells("family-1-full", "process_orders"); e1["experiment"] = 0
    e2 = _cells("family-2-full", "summarise_transactions"); e2["experiment"] = 1
    d = pd.concat([e1, e2], ignore_index=True)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = smf.logit("success ~ orchestrator * experiment", data=d).fit(disp=0)
    p = model.pvalues["orchestrator:experiment"]
    print(f"n = {len(d)} runs (n=4 conflicting, peer vs orchestrator, all policies)")
    print(f"cross-experiment interaction p = {p:.3f}")
    print("inconclusive (exploratory; the pre-registered H3 test is the "
          "within-Experiment-2 Fisher test)")


if __name__ == "__main__":
    main()
