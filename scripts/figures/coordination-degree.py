#!/usr/bin/env python3
"""Effective coordination out-degree vs agent count, against the clique
reference n-1, under the LOCKED definitions. 2x2 grid: rows = family, columns =
draw (solo, peer, reported separately, never pooled). Each panel shows the
team-level threshold sweep (t in {1,2,3,5}; t=1 hugs the clique, t>=2 grows slower)
and the participant-level (/qualifying senders) t>=2 line. Allowed, clean.

Reads:
  data/derived/messaging-structure-cells.csv
Writes:
  paper/figures/coordination-degree.png
"""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt

REPO_ROOT = Path(__file__).resolve().parents[2]
CELL_CSV = REPO_ROOT / "data" / "derived" / "messaging-structure-cells.csv"
OUT_PNG = REPO_ROOT / "figures" / "coordination-degree.png"

N_VALUES = (2, 4, 8)
FAMILIES = [("process_orders", "Experiment 1"),
            ("summarise_transactions", "Experiment 2")]
DRAWS = ("solo", "peer")
# The two flat collections are the same configuration collected twice; the
# stored topology values are historical labels, so panels are titled neutrally.
DRAW_LABELS = {"solo": "collection A", "peer": "collection B"}
TEAM = [(1, "#9ecae1", "o"), (2, "#4292c6", "s"),
        (3, "#08519c", "^"), (5, "#03306b", "D")]


def load():
    with CELL_CSV.open() as f:
        return list(csv.DictReader(f))


def series(rows, prefix, draw, col):
    out = {}
    for r in rows:
        if (r["instance_prefix"] == prefix and r["draw"] == draw
                and r["policy"] == "allowed" and r["pattern"] == "clean"):
            try:
                out[int(r["n"])] = float(r[col])
            except (ValueError, KeyError):
                pass
    return [out.get(n) for n in N_VALUES]


def main():
    rows = load()
    fig, axes = plt.subplots(2, 2, figsize=(9, 7), sharex=True, sharey=True)
    for i, (prefix, fam) in enumerate(FAMILIES):
        for j, draw in enumerate(DRAWS):
            ax = axes[i][j]
            ax.plot(N_VALUES, [n - 1 for n in N_VALUES], "--", color="black",
                    linewidth=1.3, label="clique $n-1$")
            for t, colour, marker in TEAM:
                ys = series(rows, prefix, draw, f"eff_team_t{t}")
                xs = [n for n, y in zip(N_VALUES, ys) if y is not None]
                ax.plot(xs, [y for y in ys if y is not None], marker=marker,
                        color=colour, label=f"team $t\\geq{t}$")
            yp = series(rows, prefix, draw, "eff_part_t2")
            xp = [n for n, y in zip(N_VALUES, yp) if y is not None]
            ax.plot(xp, [y for y in yp if y is not None], marker="x",
                    color="#d84315", linestyle=":",
                    label="participant $t\\geq2$")
            ax.set_xscale("log"); ax.set_xticks(N_VALUES)
            ax.set_xticklabels(N_VALUES)
            ax.set_title(f"{fam} — {DRAW_LABELS[draw]}", fontsize=9)
            ax.grid(True, which="both", alpha=0.2)
            if i == 1:
                ax.set_xlabel("agents $n$")
            if j == 0:
                ax.set_ylabel("mean effective out-degree")
            if i == 0 and j == 0:
                ax.legend(fontsize=6.5, loc="upper left", ncol=2)
    fig.suptitle("Effective coordination out-degree vs the clique line "
                 "(allowed, clean): the sustained ($t{\\geq}2$) layer "
                 "grows more slowly than the clique", fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(OUT_PNG, dpi=200)
    print(f"wrote {OUT_PNG}")


if __name__ == "__main__":
    main()
