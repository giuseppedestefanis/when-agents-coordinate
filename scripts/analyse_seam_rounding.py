#!/usr/bin/env python3
"""Seam audit: did the eight-agent compute_invoices teams discuss rounding?

Section~\\ref{sec:leadership} of the paper states that the rounding convention at
the compute_tax / format_invoices seam was discussed in all ten eight-agent
runs. That is a claim about message *content*, so it is not derivable from the
CSV-only master tables (which carry message sizes and token estimates, not
text). This script reproduces it from the per-run message transcripts, and its
committed result is `data/derived/seam-rounding-audit.csv`.

The per-run transcripts (`data/compute-invoices-scaling/runs/<run_id>/messages.jsonl`)
ship in the full-data tarball, not in the CSV-only distribution. If they are
absent this script prints a notice and leaves the committed CSV in place.
"""
from __future__ import annotations
import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "data" / "compute-invoices-scaling" / "runs"
OUT = ROOT / "data" / "derived" / "seam-rounding-audit.csv"
ROUND = re.compile(r"round", re.IGNORECASE)


def main():
    run_dirs = sorted(p for p in RUNS.glob("*a8*") if p.is_dir()) if RUNS.exists() else []
    if not run_dirs:
        print(f"per-run transcripts not present under {RUNS}")
        print("(they ship in the full-data tarball, not the CSV-only package);")
        print(f"the committed result is at {OUT}")
        return
    rows = []
    for d in run_dirs:
        mlog = d / "messages.jsonl"
        discussed, n = False, 0
        if mlog.exists():
            for line in mlog.open():
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if e.get("event") == "message":
                    n += 1
                    if ROUND.search(str(e.get("content", ""))):
                        discussed = True
        rows.append((d.name, n, discussed))
    with OUT.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["run_id", "n_messages", "rounding_discussed"])
        for rid, n, d in rows:
            w.writerow([rid, n, d])
    hit = sum(1 for _, _, d in rows if d)
    print(f"rounding discussed in {hit}/{len(rows)} eight-agent runs")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
