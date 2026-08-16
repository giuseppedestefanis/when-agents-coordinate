#!/usr/bin/env python3
"""Analyse the Family 1 broader pilot results.

Reads master/runs.csv from an experiment root, aggregates per-cell statistics,
and identifies the failing tests for each verifier-failed run by re-running
pytest against the saved solution.py with the run's own verifier copy. The
run's verifier directory contains only verifier.py (no reference solution), so
this reproduces the runner's verifier exactly.

Usage:

    .venv/bin/python scripts/analyse_pilot.py
"""

import argparse
import csv
import os
import subprocess
import sys
from collections import defaultdict
from statistics import mean

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_runs(path):
    with open(path, "r", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        r["pattern"] = (r["instance"].split("/", 1)[1]
                        if "/" in r["instance"] else "")
        r["task"] = (r["instance"].split("/", 1)[0]
                     if r.get("instance") else "")
        for c in ("n_agent_to_agent", "n_agent_to_file", "n_file_to_agent"):
            r[c] = int(r[c]) if r[c] else 0
        try:
            r["n_file_nodes"] = (float(r["n_file_nodes"])
                                 if r.get("n_file_nodes") not in (None, "")
                                 else None)
        except (ValueError, TypeError):
            r["n_file_nodes"] = None
        r["agent_count"] = int(r["agent_count"])
        r["success_bool"] = r["success"] == "True"
    return rows


def exact_mannwhitney_p(x, y):
    """Exact two-sided Mann-Whitney p-value by full permutation enumeration.

    Ties-safe, unlike scipy's normal approximation (which is unreliable at the
    pilot's N=6 with heavy ties). Two-sided p = fraction of all C(N, nx) group
    assignments whose U statistic deviates from the null mean nx*ny/2 by at
    least the observed deviation. Returns (p, U_observed, n_permutations).
    """
    import itertools
    nx, ny = len(x), len(y)
    pooled = list(x) + list(y)
    N = nx + ny

    def u_stat(a, b):
        return sum(1.0 if ai > bi else 0.5 if ai == bi else 0.0
                   for ai in a for bi in b)

    obs = u_stat(x, y)
    mu = nx * ny / 2.0
    dev = abs(obs - mu)
    count = total = 0
    for comb in itertools.combinations(range(N), nx):
        cs = set(comb)
        a = [pooled[i] for i in range(N) if i in cs]
        b = [pooled[i] for i in range(N) if i not in cs]
        if abs(u_stat(a, b) - mu) >= dev - 1e-9:
            count += 1
        total += 1
    return (count / total if total else float("nan")), obs, total


def policy_file_count_contrasts(rows):
    """§5.4 pilot file-count policy contrasts.

    Cells: n=4, clean, peer+orchestrator; metric n_file_nodes; pooled by
    artefact policy (N=6 per policy). The task is auto-selected as the one that
    spans all three policies in these cells -- process_orders for the Family-1
    pilot (the experiment §5.4 refers to), summarise_transactions for the
    Family-2 pilot -- so the script computes the right family for whichever
    --experiment-root is passed. Reports scipy's tie-corrected normal
    approximation AND the exact permutation p-value; at N=6 with ties the exact
    test is authoritative. No-ops if no task spans all three policies.
    """
    try:
        from scipy import stats as ss
    except ImportError:
        ss = None
    by_task_pol = defaultdict(lambda: defaultdict(list))
    for r in rows:
        if (r["agent_count"] == 4 and r["pattern"] == "clean"
                and r["topology"] in ("peer", "orchestrator")
                and r.get("n_file_nodes") is not None):
            by_task_pol[r.get("task", "")][r["artefact_policy"]].append(
                r["n_file_nodes"])
    # primary task = spans all three policies (tie-break on total N).
    cand = [(sum(len(v) for v in pols.values()), task)
            for task, pols in by_task_pol.items()
            if all(len(pols.get(p, [])) >= 2
                   for p in ("forbidden", "allowed", "mandatory"))]
    if not cand:
        return
    _, task = max(cand)
    by_pol = by_task_pol[task]
    print(f"\n{'-' * 96}")
    print(f"§5.4 pilot file-count policy contrasts "
          f"(n=4 clean, peer+orchestrator, {task}, n_file_nodes)")
    print(f"{'-' * 96}")
    for p in ("forbidden", "allowed", "mandatory"):
        v = sorted(by_pol[p])
        print(f"  {p:9s} N={len(v)} mean={mean(v):.3f} values={[int(x) if x==int(x) else x for x in v]}")
    print(f"  {'contrast':<26}{'scipy approx':>14}{'exact perm':>14}")
    for a, b in (("forbidden", "allowed"), ("forbidden", "mandatory"),
                 ("allowed", "mandatory")):
        x, y = by_pol[a], by_pol[b]
        approx = (ss.mannwhitneyu(x, y, alternative="two-sided")[1]
                  if ss else float("nan"))
        exact, _u, _n = exact_mannwhitney_p(x, y)
        print(f"  {a + ' vs ' + b:<26}{approx:>14.4f}{exact:>14.4f}")


def per_cell_table(rows):
    cells = defaultdict(list)
    for r in rows:
        cells[(r["pattern"], r["topology"], r["artefact_policy"],
               r["agent_count"])].append(r)
    print(f"\n{'-' * 96}")
    print("Per-cell summary "
          "(a2a = agent-to-agent edges, a2f = agent-to-file, f2a = file-to-agent)")
    print(f"{'-' * 96}")
    print(f"{'pattern':<14}{'topology':<14}{'policy':<11}{'#agents':>8}"
          f"{'n':>4}{'succ':>6}  {'a2a min/mean/max':<20}"
          f"{'a2f mean':>10}{'f2a mean':>10}")
    for key in sorted(cells):
        pattern, topology, policy, count = key
        runs = cells[key]
        n = len(runs)
        succ = sum(r["success_bool"] for r in runs)
        a2a = [r["n_agent_to_agent"] for r in runs]
        a2f = [r["n_agent_to_file"] for r in runs]
        f2a = [r["n_file_to_agent"] for r in runs]
        a2a_s = f"{min(a2a)}/{mean(a2a):.1f}/{max(a2a)}"
        print(f"{pattern:<14}{topology:<14}{policy:<11}{count:>8}"
              f"{n:>4}{succ:>3}/{n:<2}  {a2a_s:<20}"
              f"{mean(a2f):>10.1f}{mean(f2a):>10.1f}")


def topology_success_breakdown(rows):
    print(f"\n{'-' * 96}")
    print("Success by topology x pattern (at 4 agents, allowed policy where"
          " pattern != clean):")
    print(f"{'-' * 96}")
    groups = defaultdict(list)
    for r in rows:
        if r["agent_count"] != 4:
            continue
        groups[(r["topology"], r["pattern"])].append(r["success_bool"])
    for (topology, pattern), bools in sorted(groups.items()):
        print(f"  {topology:<14}{pattern:<14}{sum(bools)}/{len(bools)}")


def verifier_failures(rows, runs_root):
    """Re-run the verifier for each failed run and report which tests fail."""
    print(f"\n{'-' * 96}")
    print("Verifier-failed runs: which tests fail?")
    print(f"{'-' * 96}")
    failures = [r for r in rows
                if not r["success_bool"]
                and r["n_agent_to_agent"] + r["n_agent_to_file"]
                + r["n_file_to_agent"] > 0]
    print(f"{len(failures)} verifier-failed runs (excluding rate-limited ones"
          f" with zero edges).\n")
    python = sys.executable
    for r in failures:
        run_id = r["run_id"]
        run_dir = os.path.abspath(os.path.join(runs_root, run_id))
        verifier = os.path.join(run_dir, "verifier", "verifier.py")
        workspace = os.path.join(run_dir, "workspace")
        if not (os.path.exists(verifier)
                and os.path.exists(os.path.join(workspace, "solution.py"))):
            print(f"  {run_id}: no verifier or solution on disk")
            continue
        # Use absolute paths so PYTHONPATH remains valid after cwd changes.
        env = dict(os.environ, PYTHONPATH=workspace)
        proc = subprocess.run(
            [python, "-m", "pytest", verifier, "-q", "--no-header",
             "--tb=line", "-p", "no:cacheprovider"],
            cwd=os.path.dirname(verifier), env=env,
            capture_output=True, text=True, timeout=60)
        out = proc.stdout + proc.stderr
        fails = [line.strip() for line in out.splitlines()
                 if "FAILED" in line]
        summary = next(
            (l.strip() for l in reversed(out.strip().splitlines())
             if "passed" in l or "failed" in l or "error" in l),
            "(no summary)")
        print(f"  {run_id}")
        print(f"      {summary}")
        for line in fails:
            print(f"      {line}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-root", default="data/family-1-pilot")
    args = parser.parse_args()
    runs_csv = os.path.join(args.experiment_root, "master", "runs.csv")
    runs_root = os.path.join(args.experiment_root, "runs")
    rows = load_runs(runs_csv)
    print(f"loaded {len(rows)} run rows from {runs_csv}")
    succ = sum(r["success_bool"] for r in rows)
    print(f"overall: {succ}/{len(rows)} succeeded "
          f"({100 * succ / len(rows):.0f}%)")
    per_cell_table(rows)
    topology_success_breakdown(rows)
    policy_file_count_contrasts(rows)
    verifier_failures(rows, runs_root)


if __name__ == "__main__":
    main()
