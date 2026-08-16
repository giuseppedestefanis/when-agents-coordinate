#!/usr/bin/env python3
"""Decompose per-run output tokens across edge types, by artefact policy.

The per-edge token_cost is measured on two different bases. File edges (a2f,
f2a) carry the originating turn's output tokens divided uniformly across the
turn's tool calls. Message edges (a2a) carry an estimate from the message
length (about byte_size / 4), since they come from the message log rather than
a turn's tool calls. Summing these per-edge costs by edge type therefore shows
the direction of the channel shift rather than a like-for-like token total; the
figure's y-axis is labelled a channel proxy for this reason, and the run-level
output-token totals in the paper use the model's reported figures.

The figure compares the per-edge-type means by artefact policy at three
agent counts (n=2, n=4, n=8), for both task families:

  Row 1 (Family 1 — process_orders): pooled across topologies and patterns.
  Row 2 (Family 2 — summarise_transactions): pooled across topologies and
    patterns.

Reads:
  data/family-1-full/master/runs.csv
  data/family-1-full/master/edges.csv
  data/family-2-full/master/runs.csv
  data/family-2-full/master/edges.csv

Writes:
  paper/figures/cost-analysis.png
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


REPO_ROOT    = Path(__file__).resolve().parents[2]
F1_RUNS_CSV  = REPO_ROOT / "data" / "family-1-full" / "master" / "runs.csv"
F1_EDGES_CSV = REPO_ROOT / "data" / "family-1-full" / "master" / "edges.csv"
F2_RUNS_CSV  = REPO_ROOT / "data" / "family-2-full" / "master" / "runs.csv"
F2_EDGES_CSV = REPO_ROOT / "data" / "family-2-full" / "master" / "edges.csv"
OUT_PNG      = REPO_ROOT / "figures" / "cost-analysis.png"

POLICIES   = ["forbidden", "allowed", "mandatory"]
EDGE_TYPES = ["agent_to_agent", "agent_to_file", "file_to_agent"]
EDGE_LABELS = {
    "agent_to_agent": "direct messages",
    "agent_to_file":  "file writes",
    "file_to_agent":  "file reads",
}
EDGE_COLOURS = {
    "agent_to_agent": "#1f6feb",
    "agent_to_file":  "#c08c66",
    "file_to_agent":  "#5b8c5a",
}


def _real_run(row: dict) -> bool:
    try:
        return int(row.get("total_output_tokens") or 0) > 0
    except ValueError:
        return False


def load_runs(runs_csv: Path,
              instance_prefix: str | None = None) -> dict[str, dict]:
    """Load real runs. If instance_prefix is given, restrict to matching instances."""
    runs = {}
    with runs_csv.open(newline="") as fh:
        for row in csv.DictReader(fh):
            if not _real_run(row):
                continue
            if instance_prefix is not None and not row["instance"].startswith(instance_prefix):
                continue
            try:
                n = int(row["agent_count"])
                tokens = int(row["total_output_tokens"])
            except (ValueError, KeyError):
                continue
            runs[row["run_id"]] = {
                "agent_count":       n,
                "topology":          row["topology"],
                "artefact_policy":   row["artefact_policy"],
                "total_output_tokens": tokens,
            }
    return runs


def accumulate_edge_tokens(edges_csv: Path, runs: dict) -> dict[str, dict]:
    per_run = defaultdict(lambda: {et: 0.0 for et in EDGE_TYPES})
    with edges_csv.open(newline="") as fh:
        for row in csv.DictReader(fh):
            run_id = row["run_id"]
            if run_id not in runs:
                continue
            et = row["edge_type"]
            if et not in EDGE_TYPES:
                continue
            try:
                cost = float(row["token_cost"] or 0)
            except ValueError:
                continue
            per_run[run_id][et] += cost
    return per_run


def summarise(runs: dict, edge_tokens: dict, agent_counts=(2, 4, 8)):
    samples_abs = defaultdict(list)  # (n, policy) -> list of {et: tokens}
    totals = defaultdict(list)       # (n, policy) -> list of total_output_tokens
    for run_id, info in runs.items():
        n = info["agent_count"]
        if n not in agent_counts:
            continue
        key = (n, info["artefact_policy"])
        samples_abs[key].append(edge_tokens[run_id])
        totals[key].append(info["total_output_tokens"])
    return samples_abs, totals


def report(label: str, samples_abs: dict, totals: dict) -> None:
    print(f"\nMean output tokens per run by edge type — {label}:")
    print(f"  {'cell':<18s} {'N':>4s} {'total':>9s} "
          f"{'a2a':>9s} {'a2f':>9s} {'f2a':>9s} {'remainder':>10s}")
    for key in sorted(samples_abs):
        n, p = key
        sample = samples_abs[key]
        sample_total = totals[key]
        means = {et: float(np.mean([s[et] for s in sample]))
                 for et in EDGE_TYPES}
        total_mean = float(np.mean(sample_total))
        remainder = total_mean - sum(means.values())
        cell = f"n={n} {p}"
        print(f"  {cell:<18s} {len(sample):>4d} {total_mean:>9.0f} "
              f"{means['agent_to_agent']:>9.0f} "
              f"{means['agent_to_file']:>9.0f} "
              f"{means['file_to_agent']:>9.0f} {remainder:>10.0f}")


def main():
    f1_runs  = load_runs(F1_RUNS_CSV)
    # Restrict F2 to summarise_transactions/ to exclude H6 baseline instances.
    f2_runs  = load_runs(F2_RUNS_CSV, instance_prefix="summarise_transactions/")
    print(f"loaded F1: {len(f1_runs)} real runs,  F2: {len(f2_runs)} real runs")

    f1_edge_tokens = accumulate_edge_tokens(F1_EDGES_CSV, f1_runs)
    f2_edge_tokens = accumulate_edge_tokens(F2_EDGES_CSV, f2_runs)

    f1_samples, f1_totals = summarise(f1_runs, f1_edge_tokens)
    f2_samples, f2_totals = summarise(f2_runs, f2_edge_tokens)

    report("Family 1 (process_orders)", f1_samples, f1_totals)
    report("Family 2 (summarise_transactions)", f2_samples, f2_totals)

    plt.rcParams.update({
        "font.family": "serif",
        "font.size": 9,
        "axes.labelsize": 9,
        "legend.fontsize": 7.5,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "axes.linewidth": 0.6,
        "grid.linewidth": 0.4,
    })

    fig, axes = plt.subplots(2, 3, figsize=(7.2, 5.0), sharey="row")
    width = 0.25

    for row_idx, (label, samples, totals) in enumerate([
        ("Exp 1", f1_samples, f1_totals),
        ("Exp 2", f2_samples, f2_totals),
    ]):
        for col_idx, n in enumerate((2, 4, 8)):
            ax = axes[row_idx, col_idx]
            x = np.arange(len(POLICIES))
            for j, et in enumerate(EDGE_TYPES):
                heights = []
                for p in POLICIES:
                    sample = samples.get((n, p), [])
                    if sample:
                        heights.append(float(np.mean([s[et] for s in sample])))
                    else:
                        heights.append(0.0)
                ax.bar(x + (j - 1) * width, heights, width,
                       color=EDGE_COLOURS[et],
                       label=EDGE_LABELS[et] if (row_idx == 0 and col_idx == 2) else None,
                       edgecolor="black", linewidth=0.5, zorder=3)
            ax.set_xticks(x)
            ax.set_xticklabels(POLICIES)
            ax.set_xlabel("file policy")
            ax.set_title(f"{label}: $n={n}$ agents", fontsize=9)
            ax.grid(True, axis="y", linestyle=":", color="0.85", zorder=1)
        axes[row_idx, 0].set_ylabel("mean tokens per run (channel proxy)")

    handles, labels = axes[0, 2].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=3, frameon=False,
               fontsize=8, bbox_to_anchor=(0.5, 1.0))

    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(OUT_PNG, dpi=300, bbox_inches="tight")
    print(f"\nwrote {OUT_PNG}")


if __name__ == "__main__":
    main()
