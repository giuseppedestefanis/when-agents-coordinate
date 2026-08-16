#!/usr/bin/env python3
"""Channel-specific linearisation: directed messages (M_dir), file writes (W),
reads (R) and total coordination edges (C) vs agent count, log-log, with
slope-1 (linear) and slope-2 (quadratic) reference lines, allowed vs mandatory,
per family (peer draw). Shows that the n^2 is the directed-message channel and
that mandating files lowers the total-C exponent on the distributed task
(Family 1) but not on Family 2.

Reads:  data/derived/channel-scaling-cells.csv
Writes: paper/figures/channel-linearisation.png

(Companion to the committed channel-scaling.py / fanout-phi.py; the latter
already carries the readers-per-written-file panel.)
"""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
CELL_CSV = REPO_ROOT / "data" / "derived" / "channel-scaling-cells.csv"
OUT_PNG = REPO_ROOT / "figures" / "channel-linearisation.png"

N_VALUES = (2, 4, 8)
FAMILIES = [("process_orders", "Experiment 1 (distributed)"),
            ("summarise_transactions", "Experiment 2 (chained)")]
POLICIES = ("allowed", "mandatory")
CHANNELS = [("M_dir_mean", "M_dir_slope", "M_dir", "#1f6feb", "o"),
            ("W_mean", "W_slope", "W", "#2e7d32", "s"),
            ("R_mean", "R_slope", "R", "#d84315", "^"),
            ("C_mean", "C_slope", "C", "#6a1b9a", "D")]


def load():
    with CELL_CSV.open() as f:
        return list(csv.DictReader(f))


def slope_val(rows, fam, policy, col):
    """Per-run OLS slope from the committed CSV (matches the manuscript text)."""
    for r in rows:
        if (r["family"] == fam and r["draw"] == "peer"
                and r["policy"] == policy):
            try:
                return float(r[col])
            except (ValueError, KeyError):
                pass
    return None


def series(rows, fam, policy, col):
    out = {}
    for r in rows:
        if (r["family"] == fam and r["draw"] == "peer"
                and r["policy"] == policy):
            try:
                out[int(r["n"])] = float(r[col])
            except (ValueError, KeyError):
                pass
    return [out.get(n) for n in N_VALUES]


def main():
    rows = load()
    fig, axes = plt.subplots(2, 2, figsize=(9, 7.2), sharex=True)
    for i, (fam, flabel) in enumerate(FAMILIES):
        for j, pol in enumerate(POLICIES):
            ax = axes[i][j]
            anchor = None
            for col, slope_col, label, colour, marker in CHANNELS:
                ys = series(rows, fam, pol, col)
                xs = [n for n, y in zip(N_VALUES, ys) if y and y > 0]
                yy = [y for y in ys if y and y > 0]
                if len(xs) < 2:
                    continue
                slope = slope_val(rows, fam, pol, slope_col)
                lbl = f"{label} ({slope:.2f})" if slope is not None else label
                ax.plot(xs, yy, marker=marker, color=colour, label=lbl)
                if col == "C_mean":
                    anchor = yy[0]
            # slope-1 and slope-2 reference lines anchored at the C n=2 point
            if anchor:
                ax.plot(N_VALUES, [anchor * (n / 2) for n in N_VALUES], ":",
                        color="grey", lw=1, label="slope 1 (linear)")
                ax.plot(N_VALUES, [anchor * (n / 2) ** 2 for n in N_VALUES],
                        "--", color="grey", lw=1, label="slope 2 ($n^2$)")
            ax.set_xscale("log"); ax.set_yscale("log")
            ax.set_xticks(N_VALUES); ax.set_xticklabels(N_VALUES)
            ax.set_title(f"{flabel} — {pol}", fontsize=9)
            ax.grid(True, which="both", alpha=0.2)
            if i == 1:
                ax.set_xlabel("agents $n$")
            if j == 0:
                ax.set_ylabel("per-run mean edge count")
            ax.legend(fontsize=6.5, loc="upper left", ncol=2)
    fig.suptitle("Coordination cost by channel: mandating files lowers the "
                 "total on Experiment 1, not Experiment 2", fontsize=9.5)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(OUT_PNG, dpi=200)
    print(f"wrote {OUT_PNG}")


if __name__ == "__main__":
    main()
