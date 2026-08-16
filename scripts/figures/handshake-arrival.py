#!/usr/bin/env python3
"""Edge-arrival curve: cumulative fraction of a run's eventual distinct
directed pairs that have first appeared by normalised time tau, one line per n,
per family x draw. A curve that rises steeply and plateaus well before tau=1 is
the opening-handshake signature (the n^2 graph forms early; the rest of the run
is repeat traffic on the established core).

Reads:  data/derived/handshake-arrival-curves.csv
Writes: paper/figures/handshake-arrival.png
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt

REPO_ROOT = Path(__file__).resolve().parents[2]
CURVE_CSV = REPO_ROOT / "data" / "derived" / "handshake-arrival-curves.csv"
OUT_PNG = REPO_ROOT / "figures" / "handshake-arrival.png"

FAMILIES = [("process_orders", "Experiment 1"),
            ("summarise_transactions", "Experiment 2")]
DRAWS = ("solo", "peer")
# The two flat collections are the same configuration collected twice; the
# stored topology values are historical labels, so panels are titled neutrally.
DRAW_LABELS = {"solo": "collection A", "peer": "collection B"}
NCOL = {"2": "#9ecae1", "4": "#4292c6", "8": "#08519c"}


def load():
    rows = defaultdict(list)
    with CURVE_CSV.open() as f:
        for r in csv.DictReader(f):
            rows[(r["family"], r["draw"], r["n"])].append(
                (float(r["tau"]), float(r["cum_frac_dir"])))
    return rows


def main():
    rows = load()
    fig, axes = plt.subplots(2, 2, figsize=(9, 7), sharex=True, sharey=True)
    for i, (fam, flabel) in enumerate(FAMILIES):
        for j, draw in enumerate(DRAWS):
            ax = axes[i][j]
            for n in ("2", "4", "8"):
                pts = sorted(rows.get((fam, draw, n), []))
                if not pts:
                    continue
                ax.plot([p[0] for p in pts], [p[1] for p in pts],
                        color=NCOL[n], marker="", label=f"n={n}")
            ax.axhline(0.9, color="grey", ls=":", lw=0.8)
            ax.set_title(f"{flabel} — {DRAW_LABELS[draw]}", fontsize=9)
            ax.grid(True, alpha=0.2)
            if i == 1:
                ax.set_xlabel(r"normalised time $\tau$")
            if j == 0:
                ax.set_ylabel("cum. fraction of distinct\ndirected pairs")
            if i == 0 and j == 0:
                ax.legend(fontsize=8, loc="lower right")
    fig.suptitle("Edge-arrival curve: the directed graph forms early and "
                 "plateaus (opening handshake)", fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(OUT_PNG, dpi=200)
    print(f"wrote {OUT_PNG}")


if __name__ == "__main__":
    main()
