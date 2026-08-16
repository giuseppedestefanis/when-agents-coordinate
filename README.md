# Replication package — "When Agents Coordinate: Measuring Coordination in Multi-Agent AI Coding"

Everything behind the paper: the released dataset (1,902 graded runs, each
recorded as a temporal network with agents and files as nodes), the
infrastructure that created it, and the scripts that reproduce the load-bearing
numbers and every data figure in the paper.

This package is **CSV-only**: the per-experiment `ledger.json` files have been
removed. Nothing needed to check the paper depends on them.

## Authors

- **Giuseppe Destefanis** — Department of Computer Science, University College London, UK — g.destefanis@ucl.ac.uk
- **Tomaso Aste** — Department of Computer Science, University College London, UK — t.aste@ucl.ac.uk

**Terminology.** The paper calls the two task families **Experiment 1
(distributed)** and **Experiment 2 (chained)**. In this package the dataset
directories and run-ids keep the historical labels `family-1` and `family-2`
respectively. The two flat collection sessions (the paper's *collection A* and
*collection B*) appear under the historical topology labels `solo` and `peer`;
above one agent they are wired identically and differ only in when they were
collected. The paper's *coordinator* condition appears under the historical
topology label `orchestrator`, and the paper's *file policy* is the dataset
column `artefact_policy`.

## Start here: check the paper in two commands

First install the dependencies (pandas, numpy, scipy, networkx, statsmodels,
matplotlib, pytest):

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

**1. Verify the load-bearing numbers in the paper.**

```
.venv/bin/python scripts/verify_claims.py
```

Recomputes **112** quantitative claims from `data/` and prints each next to
the value the paper states: run counts, the table cells, the scaling
exponents with their confidence intervals, the task-shaped topology (degree and
clustering), the files output-token savings and cached-token volume, the main
percentages and test statistics, the disparity-filter backbone, the exploratory
cross-experiment H3 interaction, the seam-rounding audit, and the exploratory
regression. Expect `RESULT: 112/112 checks passed`. It covers the load-bearing numbers; a few values described in the paper are not among the automated checks.

```
.venv/bin/python scripts/verify_method_statistics.py
```

Recomputes the four method-specific statistics separately, with the estimator
each one was registered with. Expect `RESULT: 4/4`.

**2. Regenerate every data figure.**

```
.venv/bin/python scripts/figures/make_all_figures.py
```

Writes all eight data-derived figures into `figures/`, matching the ones
printed in the manuscript. The three schematic figures are data-free TikZ
drawings; their sources are in `figures/tikz/`. `REPRODUCE.md` §7 has the
figure-to-script-to-data map.

**3. Optional: run the infrastructure test suite.**

```
.venv/bin/python -m pytest tests/ -q
```

203 tests, covering the parser, the message protocol, the task generator and
the analysis scripts.

Re-collecting the dataset from zero needs a Claude subscription and is
described in `REPRODUCE.md`; checking the paper does not require it.

## The sealed replication (containment)

A validity check found that the agents in the main collection were not confined
to their working directory and read the hidden grading suite (234 runs) and the
reference solution (77 runs). To measure the findings without that access, the
load-bearing Experiment 1 (distributed) cells at eight agents were re-run in a sealed environment,
with decoys standing in for the hidden files so every reach is recorded and
nothing real is returned. The batch is 244 runs, released under
`data/sealed-replication/`.

```
.venv/bin/python scripts/analyse_sealed_replication.py
```

Reprints, from the sealed CSVs alone: the model was pinned throughout and no
read reached a real grading file; the teams still reached for the hidden test
file in 80% of runs, another agent's prompt in 66%, and the manifest in 61%;
naming a coordinator makes no difference under any file policy (all null); and
mandating shared files collapses one-to-one messaging. The seal implementation
and the read-classification script are in `sealed-runner/`.

## Where the paper's claims live

| To check | Run |
|---|---|
| the load-bearing numbers in the text, tables and captions | `scripts/verify_claims.py` |
| H6, the disparity-filter backbone, centralisation (supporting analysis) | `scripts/verify_method_statistics.py` |
| the network-structure statistics behind Finding 3 | `scripts/analyse_network_structure.py` |
| the sealed replication (containment section) | `scripts/analyse_sealed_replication.py` |
| the containment exclusion re-test and dilution comparison | `scripts/analyse_exclusion_retest.py` |
| any figure | `scripts/figures/<figure-name>.py` |

## Layout

```
README.md            this file (start here)
REPRODUCE.md         step-by-step reproduction guide
preregistration/     the four pre-registration records for H1-H8 (+ README map)
docs/
  COMPONENTS.md      the four infrastructure components + the scripts
  TASKS.md           the task library: families, verifiers, robustness instances
requirements.txt     pyproject.toml
agent_comms/         instrumentation source: message_protocol/, parser/,
                     task_generator/, runner/
tasks/               runnable task definitions, verifiers, reference solutions
tests/               infrastructure test suite (203 tests)
scripts/             verify_claims.py · verify_method_statistics.py ·
                     analyse_* (analysis) · run_* (collection) · the guardian
                     wrapper · figures/ (one script per figure +
                     make_all_figures.py)
figures/             regenerated figure output · tikz/ (schematic sources)
memory/experiments/  collection-time preliminary reports, one per full
                     schedule: the per-cell tables and top-up flags as
                     recorded during collection
data/
  README.md          full schema of the four CSV tables
  family-1-full/     850 runs   } the two full schedules
  family-2-full/     870 runs   } (family-1 = Experiment 1 distributed,
                                   family-2 = Experiment 2 chained)
  compute-invoices-scaling/  30 runs  } the two scaling arms of the chained
  h8-16agent/                70 runs  } experiment (8-step and 16-step)
  family-1-pilot/ family-2-pilot/ family-1-ablation/ family-1-spec-check/
                     pilots and design checks, 82 runs
  derived/           cell-level CSVs produced by the analyse_* scripts and
                     read by three figure scripts
  (each experiment: master/ with nodes, edges, turns and runs CSVs)
```

## What the data contains

The four CSV tables per experiment record the **structure** of every run: who
messaged whom, which files were written and read, when, at what byte size and
token cost, and whether the run passed its test suite. They do **not** contain
message text; the graph is built from logged tool-call events only.

The per-run raw directories (session JSONL, workspaces) are excluded for size.
The master CSVs are their complete parsed form, and the load-bearing statistics
and every data figure derive from them. One claim is the exception, because it
rests on message *content*, which the master CSVs do not carry: the seam result
that rounding was discussed in all ten eight-agent `compute_invoices` runs. It
ships as a committed derived table (`data/derived/seam-rounding-audit.csv`,
regenerable from the per-run transcripts in the full-data tarball via
`scripts/analyse_seam_rounding.py`). The containment read counts are file-read
paths and derive from `edges.csv` as usual; the exploratory cross-experiment H3
interaction has its own committed script (`scripts/analyse_h3_interaction.py`).

All runs were collected with Claude Code (2.1.x), model pinned to
`claude-sonnet-4-6` and recorded on every turn.
