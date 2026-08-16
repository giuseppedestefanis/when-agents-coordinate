#!/usr/bin/env python3
"""Autonomous resume loop for the sealed replication.

Runs the remaining cells to N=30 each, retrying through subscription rate-limit
pauses, for a bounded window. Each iteration relaunches run_canary (which resumes
from the ledger); when the window is capped the run pauses in seconds, so we wait
before retrying, and when it is open we make real progress.

Only ONE of these should run at a time (the runner has no run-level parallelism
and the seal's isolation assumes one run on disk at once).
"""

import json
import subprocess
import time
from collections import Counter

PY = "<repo>/.venv/bin/python"
CANARY = ("<repo>/"
          "improvement_20_july/sealed-runner/run_canary.py")
ROOT = ("<repo>/"
        "improvement_20_july/test-output/replication")
CTRL = ("/private/tmp/claude-501/-Users-<user>-Documents-paper-"
        "with-Tomaso/<session>/scratchpad/sealed-ctrl")

# Cells still to fill to 30 (forbidden pair already complete).
CELLS = [
    "conflicting-a8-orchestrator-allowed",
    "conflicting-a8-peer-allowed",
    "conflicting-a8-orchestrator-mandatory",
    "conflicting-a8-peer-mandatory",
    "clean-a8-peer-allowed",      # Block B (files finding)
    "clean-a8-peer-mandatory",    # Block B (files finding)
]
TARGET = 30
WINDOW_S = 19 * 3600
WAIT_CAPPED_S = 2400   # 40 min when a retry made no progress (window closed)
WAIT_PROGRESS_S = 60   # short pause when a retry did make progress


def counts():
    led = json.load(open(ROOT + "/ledger.json"))
    recs = led.get("records", led)
    c = Counter()
    for x in (recs.values() if isinstance(recs, dict) else recs):
        if x.get("status") == "ok":
            k = x["run_id"].replace("family-1-process_orders-", "").rsplit("-r", 1)[0]
            c[k] += 1
    return c


def all_done(c):
    return all(c.get(k, 0) >= TARGET for k in CELLS)


def main():
    deadline = time.time() + WINDOW_S
    it = 0
    while time.time() < deadline:
        c = counts()
        print(f"[loop {it}] counts: " +
              ", ".join(f"{k.split('a8-')[-1]}={c.get(k,0)}" for k in CELLS),
              flush=True)
        if all_done(c):
            print("ALL_DONE", flush=True)
            break
        before = sum(c.get(k, 0) for k in CELLS)
        cmd = [PY, CANARY, "--experiment-root", ROOT, "--control-root", CTRL,
               "--model", "claude-sonnet-4-6", "--start", "101", "--reps", "30"]
        for k in CELLS:
            cmd += ["--only-cell-pattern", "process_orders-" + k]
        subprocess.run(cmd)
        after = sum(counts().get(k, 0) for k in CELLS)
        progress = after - before
        it += 1
        print(f"[loop {it}] progress this pass: {progress}", flush=True)
        if time.time() >= deadline or all_done(counts()):
            continue
        time.sleep(WAIT_PROGRESS_S if progress > 0 else WAIT_CAPPED_S)
    print("RESUME LOOP ENDED", flush=True)


if __name__ == "__main__":
    main()
