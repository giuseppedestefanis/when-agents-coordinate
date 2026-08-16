#!/usr/bin/env python3
"""Render the agent-count scaling figure with pilot and full-schedule data.

Three data sources, plotted together on the same log-log axes:
  - F1 pilot: 3 runs per agent count at peer/allowed/clean from
    data/family-1-pilot/master/runs.csv.
  - F1 full schedule: 10 runs per agent count at peer/allowed/clean from
    data/family-1-full/master/runs.csv (rows with total_output_tokens > 0
    only, to exclude residual error rows).
  - F2 full schedule: 10 runs per agent count at peer/allowed/clean from
    data/family-2-full/master/runs.csv (rows with total_output_tokens > 0
    only).
  - compute_invoices scaling arm: 10 runs per agent count at peer/allowed/clean
    from data/compute-invoices-scaling/master/runs.csv (the H7 8-step chain;
    full decomposition reached at n=8, not n=4).
  - process_billing 16-agent arm: 20 runs per agent count at peer/allowed/clean
    from data/h8-16agent/master/runs.csv (the H8 16-step chain; n in {4,8,16},
    no idle agents, full decomposition at n=16; the mandatory n=16 cell is
    excluded from this allowed-only scaling series).

The reference line a = (33/16) * n^2 is anchored to the F1 pilot's n=4
mean (the value 33). The reference is illustrative; the slope between
the F1 full schedule's n=2 and n=4 means (6.1 and 28.5) is 2.22 and
between F2 full n=2 and n=4 (4.5 and 19.8) is 2.14, both inside the
pilot's 95% CI [1.74, 2.27].

Output:
    paper/figures/agent-scaling.png (300 dpi)
"""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


REPO_ROOT     = Path(__file__).resolve().parents[2]
F1_PILOT_CSV  = REPO_ROOT / "data" / "family-1-pilot" / "master" / "runs.csv"
F1_FULL_CSV   = REPO_ROOT / "data" / "family-1-full"  / "master" / "runs.csv"
F2_FULL_CSV   = REPO_ROOT / "data" / "family-2-full"  / "master" / "runs.csv"
CI_CSV        = REPO_ROOT / "data" / "compute-invoices-scaling" / "master" / "runs.csv"
H8_CSV        = REPO_ROOT / "data" / "h8-16agent" / "master" / "runs.csv"
OUT_PNG       = REPO_ROOT / "figures" / "agent-scaling.png"


def _real_run(row: dict) -> bool:
    try:
        return int(row.get("total_output_tokens") or 0) > 0
    except ValueError:
        return False


def load_scaling_rows(path: Path,
                      instance: str,
                      require_real: bool = False) -> list[tuple[int, int]]:
    """Return [(agent_count, a2a)] for peer/allowed/<instance> runs."""
    rows: list[tuple[int, int]] = []
    with path.open(newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            if not (
                row["topology"] == "peer"
                and row["artefact_policy"] == "allowed"
                and row["instance"] == instance
            ):
                continue
            if require_real and not _real_run(row):
                continue
            rows.append((int(row["agent_count"]), int(row["n_agent_to_agent"])))
    return rows


def by_n(rows: list[tuple[int, int]]) -> dict[int, list[int]]:
    out: dict[int, list[int]] = {}
    for n, a in rows:
        out.setdefault(n, []).append(a)
    return out


def main() -> None:
    f1_pilot = by_n(load_scaling_rows(F1_PILOT_CSV, "process_orders/clean"))
    f1_full  = by_n(load_scaling_rows(F1_FULL_CSV,  "process_orders/clean", require_real=True))
    f2_full  = by_n(load_scaling_rows(F2_FULL_CSV,  "summarise_transactions/clean", require_real=True))
    ci_full  = by_n(load_scaling_rows(CI_CSV,        "compute_invoices/clean", require_real=True))
    h8_full  = by_n(load_scaling_rows(H8_CSV,        "process_billing/clean", require_real=True))

    f1_pilot_ns = sorted(f1_pilot)
    f1_full_ns  = sorted(f1_full)
    f2_full_ns  = sorted(f2_full)
    ci_full_ns  = sorted(ci_full)
    h8_full_ns  = sorted(h8_full)

    f1_pilot_means = {n: float(np.mean(f1_pilot[n])) for n in f1_pilot_ns}
    f1_full_means  = {n: float(np.mean(f1_full[n]))  for n in f1_full_ns}
    f2_full_means  = {n: float(np.mean(f2_full[n]))  for n in f2_full_ns}
    ci_full_means  = {n: float(np.mean(ci_full[n]))  for n in ci_full_ns}
    h8_full_means  = {n: float(np.mean(h8_full[n]))  for n in h8_full_ns}

    print("--- F1 pilot (peer/allowed/clean) ---")
    for n in f1_pilot_ns:
        print(f"  n={n}: N={len(f1_pilot[n])} mean={f1_pilot_means[n]:.2f}")
    print("--- F1 full schedule (peer/allowed/clean) ---")
    for n in f1_full_ns:
        print(f"  n={n}: N={len(f1_full[n])} mean={f1_full_means[n]:.2f}")
    print("--- F2 full schedule (peer/allowed/clean) ---")
    for n in f2_full_ns:
        print(f"  n={n}: N={len(f2_full[n])} mean={f2_full_means[n]:.2f}")
    print("--- compute_invoices scaling arm (peer/allowed/clean) ---")
    for n in ci_full_ns:
        print(f"  n={n}: N={len(ci_full[n])} mean={ci_full_means[n]:.2f}")
    print("--- process_billing 16-agent arm (peer/allowed/clean) ---")
    for n in h8_full_ns:
        print(f"  n={n}: N={len(h8_full[n])} mean={h8_full_means[n]:.2f}")

    # Reference: a = (33/16) n^2, anchored to the F1 pilot's n=4 mean (33).
    coeff = f1_pilot_means[4] / (4 ** 2)
    ref_x = np.linspace(1.6, 18, 200)
    ref_y = coeff * ref_x ** 2

    plt.rcParams.update(
        {
            "font.family": "serif",
            "font.size": 9,
            "axes.labelsize": 9,
            "legend.fontsize": 7.0,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "axes.linewidth": 0.6,
            "grid.linewidth": 0.4,
        }
    )

    fig, ax = plt.subplots(figsize=(5.5, 2.6))

    ax.plot(
        ref_x, ref_y,
        linestyle="--", color="0.55", linewidth=1.0,
        label=r"ref. $n^2$",
        zorder=1,
    )

    # F1 pilot per-run (faint background only, no legend).
    for n in f1_pilot_ns:
        ax.plot(
            [n] * len(f1_pilot[n]), f1_pilot[n],
            marker="o", linestyle="None",
            markerfacecolor="none", markeredgecolor="#aac4f0",
            markeredgewidth=0.7, markersize=4.0,
            zorder=2,
        )

    # F1 full per-run (open blue circles).
    for idx, n in enumerate(f1_full_ns):
        ax.plot(
            [n] * len(f1_full[n]), f1_full[n],
            marker="o", linestyle="None",
            markerfacecolor="none", markeredgecolor="#1f6feb",
            markeredgewidth=0.9, markersize=4.5,
            label="Exp 1 full, per run ($N{=}10$)" if idx == 0 else None,
            zorder=3,
        )
    # F1 full means (red triangles up).
    ax.plot(
        f1_full_ns, [f1_full_means[n] for n in f1_full_ns],
        marker="^", linestyle="None", color="#a62a1a",
        markersize=5.5,
        label="Exp 1 per-$n$ mean",
        zorder=5,
    )

    # F2 full per-run (open green squares).
    for idx, n in enumerate(f2_full_ns):
        ax.plot(
            [n] * len(f2_full[n]), f2_full[n],
            marker="s", linestyle="None",
            markerfacecolor="none", markeredgecolor="#2ca050",
            markeredgewidth=0.9, markersize=4.5,
            label="Exp 2 full, per run ($N{=}10$)" if idx == 0 else None,
            zorder=3,
        )
    # F2 full means (dark green squares).
    ax.plot(
        f2_full_ns, [f2_full_means[n] for n in f2_full_ns],
        marker="s", linestyle="None", color="#1a6b35",
        markersize=5.5,
        label="Exp 2 per-$n$ mean",
        zorder=5,
    )

    # compute_invoices per-run (open orange diamonds).
    for idx, n in enumerate(ci_full_ns):
        ax.plot(
            [n] * len(ci_full[n]), ci_full[n],
            marker="D", linestyle="None",
            markerfacecolor="none", markeredgecolor="#e8830c",
            markeredgewidth=0.9, markersize=4.0,
            label="compute_invoices, per run ($N{=}10$)" if idx == 0 else None,
            zorder=3,
        )
    # compute_invoices means (filled orange diamonds, dashed connector to show the n=4 break).
    ax.plot(
        ci_full_ns, [ci_full_means[n] for n in ci_full_ns],
        marker="D", linestyle="--", color="#b5651d", linewidth=0.9,
        markersize=5.5,
        label="compute_invoices per-$n$ mean",
        zorder=5,
    )

    # process_billing (H8 16-step) per-run (open purple pentagons).
    for idx, n in enumerate(h8_full_ns):
        ax.plot(
            [n] * len(h8_full[n]), h8_full[n],
            marker="p", linestyle="None",
            markerfacecolor="none", markeredgecolor="#7b3fb5",
            markeredgewidth=0.9, markersize=4.0,
            label="process_billing, per run ($N{=}20$)" if idx == 0 else None,
            zorder=3,
        )
    # process_billing means (filled purple pentagons, dashed connector; plateau 8->16).
    ax.plot(
        h8_full_ns, [h8_full_means[n] for n in h8_full_ns],
        marker="p", linestyle="--", color="#5a2d8a", linewidth=0.9,
        markersize=6.0,
        label="process_billing per-$n$ mean",
        zorder=6,
    )

    ax.set_xscale("log", base=2)
    ax.set_yscale("log", base=10)
    ax.set_xticks([2, 4, 8, 16])
    ax.set_xticklabels(["2", "4", "8", "16"])
    ax.set_yticks([5, 10, 20, 50, 100, 200])
    ax.set_yticklabels(["5", "10", "20", "50", "100", "200"])
    ax.set_xlim(1.6, 20)
    ax.set_ylim(3, 220)
    ax.set_xlabel(r"agents per run, $n$")
    ax.set_ylabel("messages per run, a2a")
    ax.grid(True, which="major", linestyle=":", color="0.85")
    ax.legend(loc="upper left", frameon=False, fontsize=6.0, ncol=2,
              columnspacing=1.0, handletextpad=0.4, labelspacing=0.3)

    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=300, bbox_inches="tight")
    print(f"\nwrote {OUT_PNG}")


if __name__ == "__main__":
    main()
