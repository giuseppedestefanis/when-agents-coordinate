#!/usr/bin/env python3
"""Precompute emergent-topology scaling numbers, per experiment, across team size.

For each flat run (allowed policy, clean split) build the sustained undirected
graph (an edge between two agents if EITHER direction carried at least two
messages in the run) and record its mean degree and global clustering
(transitivity).

Two choices keep the estimate honest and unbiased (fixed 2026-08-05):
  1. Every run in the cell is included, even runs that build no named
     agent-to-agent network at all (they contribute degree 0), so the mean is
     over the whole cell rather than only the runs that happened to message.
  2. The mean degree is taken over the FULL configured roster (all N agents),
     so an agent that sustains no channel counts as degree 0 rather than being
     dropped from the denominator.
Endpoints are restricted to the real roster agent-1..agent-N, so a hallucinated
recipient never enters the graph.

Both flat collection sessions (historical labels "solo" and "peer") are pooled.

Reads:  data/family-1-full/master/{runs,edges}.csv   (Experiment 1, distributed)
        data/family-2-full/master/{runs,edges}.csv   (Experiment 2, chained)
        data/h8-16agent/master/{runs,edges}.csv        (chained 16-step arm)
Writes: data/derived/topology-scaling.csv
"""
from __future__ import annotations
import csv
import statistics as st
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "derived" / "topology-scaling.csv"
EXPS = [
    ("exp1", "distributed", "family-1-full", "process_orders-clean", (2, 4, 8)),
    ("exp2", "chained", "family-2-full", "summarise_transactions-clean", (2, 4, 8)),
    # chained 16-step scaling arm --- the only n=16 data that exists
    ("exp2_16step", "chained (16-step)", "h8-16agent",
     "process_billing-clean", (8, 16)),
]


def _cell_runs(dataset, prefix, N):
    """Every run_id in the flat allowed/clean cell, including silent runs."""
    runs = set()
    with (ROOT / "data" / dataset / "master" / "runs.csv").open() as f:
        for r in csv.DictReader(f):
            rid = r["run_id"]
            if (f"{prefix}-a{N}-" in rid and "-allowed-" in rid
                    and ("-peer-" in rid or "-solo-" in rid)):
                runs.add(rid)
    return runs


def per_run(dataset, prefix, N):
    runs = _cell_runs(dataset, prefix, N)
    roster = {f"agent-{i}" for i in range(1, N + 1)}
    dir_counts = defaultdict(lambda: defaultdict(int))
    with (ROOT / "data" / dataset / "master" / "edges.csv").open() as f:
        for r in csv.DictReader(f):
            if r["edge_type"] != "agent_to_agent":
                continue
            rid = r["run_id"]
            if rid not in runs:
                continue
            s, t = r["source"], r["target"]
            if s == t or s not in roster or t not in roster:
                continue
            dir_counts[rid][(s, t)] += 1

    degs, cls = [], []
    for rid in runs:                       # every run in the cell, silent or not
        adj = defaultdict(set)
        for (s, t), c in dir_counts.get(rid, {}).items():
            if c >= 2:
                adj[s].add(t); adj[t].add(s)
        # mean degree over the FULL roster: isolated agents count as 0
        degs.append(sum(len(adj[n]) for n in adj) / N)
        # global clustering of whatever graph exists; empty graph -> 0
        tri = trip = 0
        for n in adj:
            nb = list(adj[n])
            for i in range(len(nb)):
                for j in range(i + 1, len(nb)):
                    trip += 1
                    if nb[j] in adj[nb[i]]:
                        tri += 1
        cls.append(tri / trip if trip else 0.0)
    built = sum(1 for rid in runs if dir_counts.get(rid))
    return degs, cls, len(runs), built


def sem(xs):
    return (st.pstdev(xs) / (len(xs) ** 0.5)) if len(xs) > 1 else 0.0


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["experiment", "label", "n", "clique",
                    "degree_mean", "degree_sem",
                    "clustering_mean", "clustering_sem", "runs", "runs_with_network"])
        for tag, label, dataset, prefix, ns in EXPS:
            for N in ns:
                degs, cls, nruns, built = per_run(dataset, prefix, N)
                w.writerow([tag, label, N, N - 1,
                            f"{st.mean(degs):.4f}", f"{sem(degs):.4f}",
                            f"{st.mean(cls):.4f}", f"{sem(cls):.4f}", nruns, built])
                print(f"{tag} n={N}: deg={st.mean(degs):.2f} clust={st.mean(cls):.2f} "
                      f"runs={nruns} built-a-network={built}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
