#!/usr/bin/env python3
"""The task shapes the network: sustained-graph density vs the clique line, and
the clustering coefficient, per experiment across team size.

Two panels. Left: mean degree of the sustained undirected graph (a pair links
once either direction has carried at least two messages) against the clique line
n-1. Right: global clustering (transitivity) of the same graph. The distributed
task rides the clique line and fills in to a near-complete, highly clustered
graph; the chained task stays sparse and its gap to the clique line widens with
n. The only 16-agent data is the chained 16-step scaling arm (process_billing).

Reads:  data/derived/topology-scaling.csv   (from precompute_topology_scaling.py)
Writes: figures/topology-density.png
"""
from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt

REPO_ROOT = Path(__file__).resolve().parents[2]
CSV_IN = REPO_ROOT / "data" / "derived" / "topology-scaling.csv"
OUT_PNG = REPO_ROOT / "figures" / "topology-density.png"

XN = [2, 4, 8, 16]
POS = {n: i for i, n in enumerate(XN)}
DIST = "#2b6cb8"
CHAIN = "#1a8a3a"


def load():
    d = {}
    with CSV_IN.open() as f:
        for r in csv.DictReader(f):
            d.setdefault(r["experiment"], {})[int(r["n"])] = r
    return d


def main():
    d = load()
    fig, (axd, axc) = plt.subplots(1, 2, figsize=(11, 4.2))

    # --- left panel: degree vs clique line ---
    axd.plot([POS[n] for n in XN], [n - 1 for n in XN], "--", color="black",
             linewidth=1.4, label="clique $n-1$ (all-to-all)")

    def deg(ax, tag, ns, colour, mk, label):
        xs = [POS[n] for n in ns]
        ys = [float(d[tag][n]["degree_mean"]) for n in ns]
        es = [float(d[tag][n]["degree_sem"]) for n in ns]
        ax.errorbar(xs, ys, yerr=es, marker=mk, color=colour, linewidth=2.2,
                    markersize=8, capsize=3, label=label)

    deg(axd, "exp1", [2, 4, 8], DIST, "o", "Experiment 1 (distributed)")
    deg(axd, "exp2", [2, 4, 8], CHAIN, "s", "Experiment 2 (chained)")
    y16 = float(d["exp2_16step"][16]["degree_mean"])
    e16 = float(d["exp2_16step"][16]["degree_sem"])
    axd.errorbar([POS[16]], [y16], yerr=[e16], marker="D", color=CHAIN,
                 markersize=9, markerfacecolor="white", markeredgewidth=1.8,
                 capsize=3, linewidth=0, label="chained, 16-step arm")
    axd.annotate(f"degree ${y16:.2f}$\nvs clique $15$", (POS[16], y16),
                 xytext=(POS[16] - 0.25, y16 + 3.2), ha="right", fontsize=9,
                 color=CHAIN,
                 arrowprops=dict(arrowstyle="->", color=CHAIN, lw=1.1))
    axd.set_xticks([POS[n] for n in XN]); axd.set_xticklabels(XN)
    axd.set_xlabel("agents $n$")
    axd.set_ylabel("mean live partners per agent")
    axd.set_title("Density vs the clique line", fontsize=10)
    axd.grid(axis="y", alpha=0.25)
    axd.legend(fontsize=8, loc="upper left")

    # --- right panel: clustering coefficient ---
    def clust(ax, tag, ns, colour, mk, label):
        xs = [POS[n] for n in ns]
        ys = [float(d[tag][n]["clustering_mean"]) for n in ns]
        es = [float(d[tag][n]["clustering_sem"]) for n in ns]
        ax.errorbar(xs, ys, yerr=es, marker=mk, color=colour, linewidth=2.2,
                    markersize=8, capsize=3, label=label)

    clust(axc, "exp1", [2, 4, 8], DIST, "o", "Experiment 1 (distributed)")
    clust(axc, "exp2", [2, 4, 8], CHAIN, "s", "Experiment 2 (chained)")
    yc16 = float(d["exp2_16step"][16]["clustering_mean"])
    ec16 = float(d["exp2_16step"][16]["clustering_sem"])
    axc.errorbar([POS[16]], [yc16], yerr=[ec16], marker="D", color=CHAIN,
                 markersize=9, markerfacecolor="white", markeredgewidth=1.8,
                 capsize=3, linewidth=0, label="chained, 16-step arm")
    axc.set_xticks([POS[n] for n in XN]); axc.set_xticklabels(XN)
    axc.set_ylim(-0.03, 1.03)
    axc.set_xlabel("agents $n$")
    axc.set_ylabel("global clustering (transitivity)")
    axc.set_title("How tightly the partners interconnect", fontsize=10)
    axc.grid(axis="y", alpha=0.25)

    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=200)
    print(f"wrote {OUT_PNG}")


if __name__ == "__main__":
    main()
