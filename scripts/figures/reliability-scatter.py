#!/usr/bin/env python3
"""Test-retest reliability scatter: solo-session vs peer-session mean a2a.

At n>=2 the `solo` and `peer` topology labels denote the SAME configuration
(identical prompts and message-protocol wiring; see the solo/peer finding). The
two labels were nevertheless run in separate sessions, so each matched cell is a
same-configuration replication at a pinned model identifier. This figure plots
the two sessions' per-cell mean a2a against each other; points on the y=x
diagonal reproduced, points off it drifted between sessions.

One point per matched (family, n, policy, pattern) cell at n in {2,4,8}. Open
markers are cells whose solo-vs-peer per-run a2a differ under a Mann-Whitney
test with a Benjamini-Hochberg correction across each experiment's cells (the
same correction the paper applies to related contrasts); filled markers agree.
Axes are symlog (linear near zero) so the near-zero Family-1 mandatory cells
remain visible.

Reads:
    data/family-1-full/master/runs.csv
    data/family-2-full/master/runs.csv
Writes:
    paper/figures/reliability-scatter.png
"""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from scipy import stats


REPO_ROOT   = Path(__file__).resolve().parents[2]
F1_CSV      = REPO_ROOT / "data" / "family-1-full" / "master" / "runs.csv"
F2_CSV      = REPO_ROOT / "data" / "family-2-full" / "master" / "runs.csv"
OUT_PNG     = REPO_ROOT / "figures" / "reliability-scatter.png"

PATTERNS = ("clean", "overlapping", "conflicting")
POLICIES = ("forbidden", "allowed", "mandatory")
NS       = ("2", "4", "8")


def _real(r: dict) -> bool:
    try:
        return int(r.get("total_output_tokens") or 0) > 0
    except ValueError:
        return False


def per_cell(path: Path, prefix: str):
    """Return {(n, policy, pattern): {'solo': [a2a...], 'peer': [a2a...]}}."""
    out: dict = {}
    with path.open(newline="") as fh:
        for r in csv.DictReader(fh):
            if not _real(r):
                continue
            if r["topology"] not in ("solo", "peer"):
                continue
            if not r["instance"].startswith(prefix):
                continue
            pattern = r["instance"][len(prefix):]
            if pattern not in PATTERNS or r["agent_count"] not in NS:
                continue
            key = (r["agent_count"], r["artefact_policy"], pattern)
            out.setdefault(key, {"solo": [], "peer": []})
            out[key][r["topology"]].append(int(r["n_agent_to_agent"]))
    return out


def _bh(pvals, alpha=0.05):
    """Benjamini-Hochberg significance flags for a set of p-values."""
    order = np.argsort(pvals)
    m = len(pvals)
    sig = np.zeros(m, bool)
    for i, idx in enumerate(order):
        if pvals[idx] <= (i + 1) / m * alpha:
            sig[order[: i + 1]] = True
    return sig


def matched(path: Path, prefix: str):
    """Yield (peer_mean, solo_mean, p, significant). Significance is
    Benjamini-Hochberg-corrected across the experiment's matched cells, to
    match the correction the paper applies to related contrasts."""
    rows = []
    for key, d in per_cell(path, prefix).items():
        if not d["solo"] or not d["peer"]:
            continue
        peer_m = float(np.mean(d["peer"]))
        solo_m = float(np.mean(d["solo"]))
        try:
            p = stats.mannwhitneyu(d["peer"], d["solo"], alternative="two-sided").pvalue
        except ValueError:
            p = 1.0
        rows.append([peer_m, solo_m, p])
    if not rows:
        return []
    sig = _bh(np.array([r[2] for r in rows]))
    return [(r[0], r[1], r[2], bool(s)) for r, s in zip(rows, sig)]


def main() -> None:
    f1 = matched(F1_CSV, "process_orders/")
    f2 = matched(F2_CSV, "summarise_transactions/")
    f1_sig = sum(1 for *_, s in f1 if s)
    f2_sig = sum(1 for *_, s in f2 if s)
    print(f"F1: {f1_sig}/{len(f1)} cells differ significantly across sessions")
    print(f"F2: {f2_sig}/{len(f2)} cells differ significantly across sessions")

    plt.rcParams.update({
        "font.family": "serif", "font.size": 9, "axes.labelsize": 9,
        "legend.fontsize": 7.5, "xtick.labelsize": 8, "ytick.labelsize": 8,
        "axes.linewidth": 0.6,
    })
    fig, ax = plt.subplots(figsize=(3.4, 3.2))

    lo, hi = 0.0, 140.0
    ax.plot([lo, hi], [lo, hi], linestyle="--", color="0.6",
            linewidth=0.9, zorder=1, label="$y=x$ (reproduced)")

    series = [("Exp 1 (process\\_orders)", f1, "#1f6feb"),
              ("Exp 2 (summarise\\_transactions)", f2, "#1a8a3a")]
    # Correct F1 label.
    series[0] = ("Exp 1 (process\\_orders)", f1, "#1f6feb")

    for label, rows, colour in series:
        for kind, sig in (("agree", False), ("differ", True)):
            xs = [r[0] for r in rows if r[3] == sig]
            ys = [r[1] for r in rows if r[3] == sig]
            ax.scatter(
                xs, ys, s=26,
                facecolors="none" if sig else colour,
                edgecolors=colour, linewidths=1.0,
                marker="o", zorder=3,
            )

    # Legend proxies.
    from matplotlib.lines import Line2D
    handles = [
        Line2D([0], [0], linestyle="--", color="0.6", label="$y=x$ (reproduced)"),
        Line2D([0], [0], marker="o", linestyle="None", markerfacecolor="#1f6feb",
               markeredgecolor="#1f6feb", label=f"Exp 1 ($\\,${f1_sig}/{len(f1)} differ)"),
        Line2D([0], [0], marker="o", linestyle="None", markerfacecolor="#1a8a3a",
               markeredgecolor="#1a8a3a", label=f"Exp 2 ($\\,${f2_sig}/{len(f2)} differ)"),
        Line2D([0], [0], marker="o", linestyle="None", markerfacecolor="white",
               markeredgecolor="0.3", label="open $=$ BH-significant"),
    ]
    ax.legend(handles=handles, loc="upper left", frameon=False)

    ax.set_xscale("symlog", linthresh=1.0)
    ax.set_yscale("symlog", linthresh=1.0)
    ax.set_xlim(0, hi)
    ax.set_ylim(0, hi)
    ax.set_xticks([0, 1, 10, 100])
    ax.set_yticks([0, 1, 10, 100])
    ax.set_xticklabels(["0", "1", "10", "100"])
    ax.set_yticklabels(["0", "1", "10", "100"])
    ax.set_xlabel("one session, mean a2a per run")
    ax.set_ylabel("other session, mean a2a per run")
    ax.grid(True, which="major", linestyle=":", color="0.88")

    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=300, bbox_inches="tight")
    print(f"wrote {OUT_PNG}")


if __name__ == "__main__":
    main()
