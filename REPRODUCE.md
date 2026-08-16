# Reproduction guide

This guide reproduces the study end to end, from environment setup to the
analysis outputs behind each research question. It is the entry point for
artefact evaluation. For the research framing and design, read `PLAN.md`;
for the data schema, read `data/README.md`; for the infrastructure and task
documentation, read `docs/COMPONENTS.md` and `docs/TASKS.md`.

A note on provenance: this guide is shared with the research repository.
References to `PLAN.md`, to `memory/...` paths, and to notes such as
`writer-reconciliation.md` point to that repository's design record, which is
not part of this package; nothing in them is needed to reproduce the paper.
The analysis scripts' default report paths use the same `memory/experiments/...`
convention; the scripts create those directories on demand, and every script
accepts `--out`/`--output` to write anywhere else.

The study characterises the communication networks that emerge in
multi-agent LLM coding systems. Each run is parsed into a heterogeneous
temporal graph (agents and files as nodes, typed information transfers as
edges) and the network structure, its dynamics and its response to
interventions are measured across a configuration matrix.

## 1. Environment

Python 3.10 or newer (developed and tested on 3.14).

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

`requirements.txt` pins the dependencies. The infrastructure tests run from
the project root and need no Claude subscription:

```
.venv/bin/python -m pytest          # full suite
```

The Family task verifiers run one instance at a time so the per-instance
`solution` module does not clash:

```
.venv/bin/python -m pytest tasks/family-1/instance-1/verifier.py
```

## 2. Two reproduction levels

The package supports two levels of reproduction.

**Level A — re-analyse the released data (no subscription needed).** The
master CSVs and ledgers for every experiment are in the repository. The
analysis scripts run directly against them and regenerate every reported
number and the figures' input. This is the level artefact evaluation
normally needs.

**Level B — re-collect the data (needs a Claude subscription).** The
experiment runner invokes the headless Claude Code command line on the
Claude subscription plan (the launcher strips `ANTHROPIC_API_KEY` so the
machine's subscription credentials are used). The machine must be signed in
to Claude Code, or have a long-lived token from `claude setup-token`.
Re-collection reproduces the data cut in distribution; agentic runs vary run-to-run, so the exact rows will differ, and the design absorbs this with N=10 per cell
(see `PLAN.md` and the per-family analysis plans).

## 3. Level A: re-analyse the released data

Each command reads `data/<experiment>/master/*.csv` (filtered to the ledger
`ok` set) and writes a report under `memory/experiments/<experiment>/`.

```
# Experiment 1 (distributed) full schedule — outcome and structure
.venv/bin/python scripts/analyse_family1_full.py

# Experiment 2 (chained) full schedule — sequential dependency
.venv/bin/python scripts/analyse_family2_full.py

# temporal dynamics metrics, either experiment
.venv/bin/python scripts/analyse_rq2_dynamics.py \
    --experiment-root data/family-1-full \
    --out memory/experiments/rq2-dynamics/family-1-preliminary.md
.venv/bin/python scripts/analyse_rq2_dynamics.py \
    --experiment-root data/family-2-full \
    --out memory/experiments/rq2-dynamics/family-2-preliminary.md

# RQ1 structural battery + RQ3 structure-outcome regressions (exploratory)
.venv/bin/python scripts/analyse_structure_outcome.py \
    --experiment-root data/family-1-full \
    --out memory/experiments/structure-outcome/family-1-preliminary.md
.venv/bin/python scripts/analyse_structure_outcome.py \
    --experiment-root data/family-2-full \
    --out memory/experiments/structure-outcome/family-2-preliminary.md

# Supporting experiments
.venv/bin/python scripts/analyse_pilot.py        # Experiment 1 broader pilot
.venv/bin/python scripts/analyse_ablation.py     # forbidden-policy ablation

# Review robustness checks (§5.4 / §5.5 / §5.6 audit)
.venv/bin/python scripts/analyse_solo_peer_reliability.py   # test-retest + decile shape (master CSVs)
.venv/bin/python scripts/analyse_clustered_contrasts.py     # session-clustered file-count contrasts + n=8 token range (master CSVs)
.venv/bin/python scripts/analyse_chain_distance.py          # Family-2 chain-distance (needs per-run dirs; see below)
.venv/bin/python scripts/analyse_classifier_accounting.py   # H5 per-category breakdown + sensitivity bounds (master CSVs); chain-distance denominator + per-run distribution + matched 2x2 (needs per-run dirs)
.venv/bin/python scripts/analyse_messaging_structure.py     # de-trivialising n^2: channel exponents (M/W/R/C + tokens), broadcast amplification, effective-degree saturation, disparity backbone (master CSVs); writes data/derived/messaging-structure-cells.csv
.venv/bin/python scripts/analyse_handshake_timing.py        # RQ1 opening-handshake-in-time: edge-arrival curve (tau50/90/complete), shallow-vs-sustained, message byte_size scaling (master CSVs); writes data/derived/handshake-timing-cells.csv + handshake-arrival-curves.csv
.venv/bin/python scripts/analyse_channel_scaling.py         # RQ1 linearisation: per-channel scaling exponents (M_dir/M_bc/W/R/C + token-cost), fan-out, allowed-vs-mandatory regime (master CSVs); writes data/derived/channel-scaling-cells.csv
```

Note for this package: the per-experiment `ledger.json` files have been removed;
this package is CSV-only. Nothing needed to reproduce the paper depends on
them (`verify_claims.py` and every figure script read only `master/*.csv`).

Data tiers: most analysis scripts read only the `master/*.csv` tables
and reproduce from a plain checkout. Two read the per-run
directories instead, which are git-ignored and ship in the released data
tarball (see `data/README.md`): `scripts/count_workspace_files.py` (end-of-run
`workspace/` listings, the §8 exception) and `scripts/analyse_chain_distance.py`
(per-run `instance.json` step maps + `datasets/edges.csv`).
`scripts/analyse_classifier_accounting.py` is mixed: its Outputs 1-2 (the H5
per-category breakdown and sensitivity bounds) read only the master CSVs, while
its Outputs 3-4 (chain-distance denominator and matched 2x2) read the same
per-run directories. Extract the tarball under `data/` before running the
per-run analyses; each prints a clear notice if the per-run directories are
absent.

The analysis scripts are deterministic on the master CSVs plus the ledger,
so a re-run on an unchanged cut reproduces the report byte for byte. Every
script filters rows against the ledger `ok` set (ghost-row protection), so
an errored or in-flight run never enters a statistic.

To rebuild the master CSVs from the per-run datasets (only needed if the
`runs/` directories are present; they are excluded from version control):

```
.venv/bin/python scripts/regenerate_datasets.py --experiment-root data/family-2-full
```

## 4. Research-question to artefact map

| RQ | Question | Data | Analysis | Output |
|----|----------|------|----------|--------|
| RQ1 | Topology: what structures emerge | `runs.csv` counts; `edges.csv` for structure | `analyse_family{1,2}_full.py`; `analyse_structure_outcome.py` (degree, clustering, modularity, centralisation) | `memory/experiments/family-{1,2}-full/preliminary.md`; `memory/experiments/structure-outcome/family-{1,2}-preliminary.md` |
| RQ2 | Dynamics: how networks evolve | `edges.csv` timestamps | `analyse_rq2_dynamics.py` | `memory/experiments/rq2-dynamics/family-{1,2}-preliminary.md` |
| RQ3 | Structure and outcome | `runs.csv`, `edges.csv`, ledger quality | `analyse_family{1,2}_full.py` (the plan's internal H1–H7, which is **not** the paper's H1–H8 numbering; see `preregistration/README.md` for the crosswalk); `analyse_structure_outcome.py` (regressions, exploratory) | full-schedule reports; `structure-outcome/family-{1,2}-preliminary.md` |
| RQ4 | Intervention (policy, topology) | `runs.csv` policy/topology axes | `analyse_family{1,2}_full.py` | same full-schedule reports |

The `analyse_structure_outcome.py` analyses (RQ1 structural battery and RQ3
regressions) are exploratory/descriptive, separate from the pre-registered
confirmatory tests; see
`memory/experiments/structure-outcome/analysis-plan.md` and the
`writer-reconciliation.md` note alongside it.

The pre-registration records are released in `preregistration/` (see
`preregistration/README.md` for the full hypothesis map and the H2/H3
qualifications). Six hypotheses are pre-registered in both prediction and test
(H1, H4--H8); H2 and H3 are qualified:

- `preregistration/experiment-2-analysis-plan.md` (H1, H4--H6, and H3 with a
  qualification)
- `preregistration/scaling-arm-8step-H7.md` (H7)
- `preregistration/scaling-arm-16step-H8.md` (H8)
- `preregistration/experiment-1-analysis-plan.md` (the top-up decision only, not
  a hypothesis; H2 is pilot-informed and analysis-specified after collection)

## 5. Level B: re-collect the data

With a Claude subscription configured (see section 2):

```
# One-run end-to-end check
.venv/bin/python scripts/smoke_run.py

# Experiment 1 broader pilot (36 runs) and the validating ablations
.venv/bin/python scripts/run_pilot.py
.venv/bin/python scripts/run_ablation.py
.venv/bin/python scripts/run_spec_check.py

# Full schedules. Long-running; run through the wall-clock guardian so a
# stalled launcher cannot hang the batch. --max-runs caps a single sitting;
# the JSON ledger makes a batch resumable (re-run to continue).
.venv/bin/python scripts/run_with_guardian.py \
    --log data/family-2-full-run.log --per-run-timeout 1000 \
    -- /usr/bin/env -u ANTHROPIC_API_KEY \
       .venv/bin/python scripts/run_family2_full.py --max-runs 50
```

`scripts/run_family1_full.py` and `scripts/run_family2_full.py` build the
pre-registered schedules. The model is pinned to `claude-sonnet-4-6` and
recorded per turn in `turns.csv`. The guardian wrapper and the launcher
defensive fixes are documented in `memory/decisions.md` (2026-05-31; research repository only).

## 6. Released data cut (provenance)

See `data/README.md` for the per-dataset table: run counts, model pin, the
part of the paper each supports, and whether the cut is complete. Both full
schedules are complete: Experiment 1 (distributed, `family-1-full`) at 850/850
and Experiment 2 (chained, `family-2-full`) at 870/870, giving the 1,720-run
grid; with the two scaling arms, the pilots and checks, and the 244-run sealed
replication, the released collection is 1,902 main runs plus 244 sealed.

## 7. Figures

Every data-derived figure in the paper is regenerated by one script under
`scripts/figures/`, reading the master CSVs (and, for three figures, the
derived-cell CSVs under `data/derived/`, themselves produced by the
`analyse_*` scripts). Regenerate all of them into `figures/` with:

```
python3 scripts/figures/make_all_figures.py
```

| figure (paper) | script | reads |
|---|---|---|
| message-count scaling | `agent-scaling.py` | full + arm `runs.csv` |
| handshake arrival curves | `handshake-arrival.py` | `data/derived/handshake-arrival-curves.csv` |
| task shapes the network (degree vs clique + clustering) | `topology-density.py` | `data/derived/topology-scaling.csv` |
| sustained out-degree vs clique (demoted directed metric) | `coordination-degree.py` | `data/derived/messaging-structure-cells.csv` |
| output tokens by channel | `cost-analysis.py` | full `runs.csv` + `edges.csv` |
| channel-specific scaling | `channel-linearisation.py` | `data/derived/channel-scaling-cells.csv` |
| test-retest reliability | `reliability-scatter.py` | full `runs.csv` |
| team structure x split success | `topology-split.py` | full `runs.csv` |

`data/derived/topology-scaling.csv` is regenerated from the master edge tables
by `scripts/precompute_topology_scaling.py`, which builds each flat run's
sustained undirected graph (an edge when either direction carried at least two
messages) and records its mean degree and global clustering; `make_all_figures.py`
runs this precompute step before drawing `topology-density.py`.

The three schematic figures (the measurement object, the pipeline, the
design at a glance) are data-free TikZ drawings; their sources are in
`figures/tikz/` and compile inside the manuscript.

## 8. Layout

See `README.md` for the full repository layout and `data/README.md` for the
dataset schema.
