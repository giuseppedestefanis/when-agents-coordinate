# data

Datasets produced by the session parser (infrastructure component 2). These
are the analysable output of the study: load them to build communication
networks and compute network statistics.

## The four CSV files

Each run parsed by the parser produces four CSV files in one directory.

- `nodes.csv` one row per node (agent or file): `run_id`, `node_id`,
  `node_type`, `label`.
- `edges.csv` one row per edge, the analysable core of the communication
  graph: `run_id`, `source`, `target`, `source_type`, `target_type`,
  `edge_type`, `subtype`, `timestamp`, `token_cost`, `byte_size`,
  `turn_uuid`, `tool`, `target_kind`.
  - `edge_type` is one of `agent_to_agent` (a message), `agent_to_file` (a
    file operation, with `subtype` create/edit/append/delete) or
    `file_to_agent` (a read).
  - `timestamp` is ISO-8601 with millisecond resolution; agent-to-agent
    timestamps come from the message-protocol log and file edges from the
    session JSONL, on the same machine clock.
  - `token_cost` is measured on two bases by edge type. For file edges it is
    the originating turn's output tokens divided equally across that turn's
    tool calls (a coarse estimate; join on `turn_uuid` to `turns.csv` for
    authoritative usage). For message edges (`agent_to_agent`) it is an
    estimate from the message length, about `byte_size / 4`, taken from the message log, and `turn_uuid` is empty.
    `byte_size` is exact.
  - `target_kind` (message edges only) classifies the addressee as
    `canonical`, `alias`, `broadcast`, `role` or `unknown`, per the
    2026-05-30 addressing convention (`agent_comms/parser/addressing.py`).
- `turns.csv` one row per model turn, with authoritative token usage:
  `run_id`, `agent`, `turn_uuid`, `timestamp`, `is_sidechain`,
  `input_tokens`, `output_tokens`, `cache_read_tokens`,
  `cache_creation_tokens`, `model`. Every edge carries a `turn_uuid` that
  joins to this table, so token analysis can use authoritative figures rather
  than the coarse `token_cost` estimate on the edge.
- `runs.csv` one row, the run-level record: `run_id`, configuration fields
  (`family`, `instance`, `agent_count`, `topology`, `artefact_policy`), the
  outcome (`success`, `completion_time_s`, `total_input_tokens`,
  `total_output_tokens`) and summary network counts (`n_nodes`, `n_edges`,
  `n_agent_nodes`, `n_file_nodes`, `n_agent_to_agent`,
  `n_agent_to_agent_directed`, `n_agent_to_file`, `n_file_to_agent`).
  `n_agent_to_agent` is the total message-event count; the
  `n_agent_to_agent_directed` subset counts messages addressed to a
  `canonical` or `alias` target (i.e. to a specific agent, excluding broadcast and role targets).

## Layout

```
data/
  <experiment>/          one folder per experiment (family-1-full, family-2-full,
                         compute-invoices-scaling, h8-16agent, the pilots, checks)
    ledger.csv           the run record and the authoritative ok-set
    master/              the per-run datasets concatenated: runs.csv, edges.csv,
                         nodes.csv, turns.csv
  derived/               cell-level CSVs from the analyse_* scripts, read by the
                         figure scripts
  sealed-replication/    the 244-run sealed containment batch (paper Section 9)
```

The `master/` datasets are what an analysis loads to build networks and
compare runs across the configuration matrix; they are produced by
`agent_comms.parser.combine_datasets`. This is the CSV-only distribution: it
ships the `master/` tables and `ledger.csv` for every experiment, which is
everything `verify_claims.py`, the analysis scripts, and the figure scripts
need. The raw per-run directories (`runs/`, with session files and workspaces)
are not included; only two auxiliary scripts read them
(`count_workspace_files.py`, `analyse_chain_distance.py`), and each prints a
notice and skips if they are absent.

## Experiment manifest

One subdirectory per experiment, each with its own `ledger.csv` (the run
record and the authoritative `ok`-set used for ghost-row filtering) and
`master/`. All runs are pinned to
`claude-sonnet-4-6`, recorded per turn in `turns.csv`. Counts below are the
released cut at the time of writing; regenerate with the analysis scripts to
confirm against the committed data.

Directory names use the historical `family-1`/`family-2` labels; in the paper
these are **Experiment 1 (distributed)** and **Experiment 2 (chained)**.

| dataset | runs (ok / err) | verifier pass | role | maps to | complete |
|------------|-----------------|---------------|------|-----|----------|
| `family-1-pilot` | 36 / 0 | 26 | Experiment 1 broader pilot (one-factor-at-a-time) | design check | yes |
| `family-1-ablation` | 3 / 0 | 3 | forbidden-policy enforcement ablation | methods validation | yes |
| `family-1-spec-check` | 3 / 0 | 3 | spec-fix re-validation (int-vs-float) | methods validation | yes |
| `family-1-full` | 850 / 0 | 754 | Experiment 1 full schedule (distributed) | RQ1, RQ2, RQ3, RQ4 | **yes** |
| `family-2-pilot` | 40 / 2 | 36 | Experiment 2 pilot (chained) | design check | yes |
| `family-2-full` | 870 / 0 | 709 | Experiment 2 full schedule (chained) | RQ1, RQ2, RQ3, RQ4 | **yes** |
| `sealed-replication` | 244 / 0 | 197 | sealed re-run of the load-bearing Experiment 1 (distributed) cells at eight agents (containment) | Containment | **yes** |

### `sealed-replication`

A separate 244-run batch, collected after a validity check found that the
agents in the main collection were reading the hidden grading suite and the
reference solution. It re-runs the load-bearing Experiment 1 (distributed) cells at eight agents
in a sealed environment: the working directory is isolated, and where the
grading suite, the reference solution, the manifest and the other agents'
prompts used to sit, a decoy of the same name carries a marked placeholder and
none of the real content. Every read is logged and classified by location, so
an agent's reach for the hidden material is recorded while the real material
stays out of view. The batch covers the six conflicting-split cells (flat and
orchestrator under each file policy) and the two clean-split file cells, all on
the same pinned model, with the grading suite byte-identical to the released
one. Paths in these CSVs are placeholders: `<control>` is the decoy tree the
agents reach into, `<home>` and `<tmp>` the model runtime's own stores.

`scripts/analyse_sealed_replication.py` reprints the sealed results from these
CSVs: how often the teams reached for each decoy (80% for the hidden test file,
67% for another agent's prompt, 61% for the manifest), the leadership contrast
under each policy (all null), and the file-policy message substitution. The
seal implementation and the read-classification script are in `sealed-runner/`.

Both full schedules are complete. All 87 Experiment 2
cell-and-pattern-and-task combinations are at N=10 (850 main matrix
+ 10 `compute_invoices` baseline + 10 `summarise_transactions_v2`
baseline). The master CSVs are the authoritative released datasets.
See `memory/status.md` for the collection history and
`memory/experiments/family-2-full/preliminary.md` for the preliminary
analysis results.

## Packaging the released artefact

The per-run directories under each `*/runs/` ship as a tarball separate from
the git repository (they are git-ignored). When building that tarball, exclude
macOS `.DS_Store` files so they do not re-accumulate in the release:

```
tar --exclude='.DS_Store' -czf data-artefact.tar.gz data/
```

Each `*/runs/<run_id>/` is one self-contained run directory (instance,
prompts, message log at n≥2, sessions, datasets, verifier, result). Nothing
else should appear at the `runs/` level; stray workspace or scratch
directories are runtime debris and are not part of the released artefact.

## Building a network from edges.csv

The `master/edges.csv` tables hold every run in an experiment, so filter to one
`run_id` to build that run's graph:

```python
import pandas as pd
import networkx as nx

edges = pd.read_csv("data/family-1-full/master/edges.csv")
one_run = edges[edges.run_id == edges.run_id.iloc[0]]
graph = nx.from_pandas_edgelist(
    one_run, "source", "target", edge_attr=True,
    create_using=nx.MultiDiGraph)
```

`networkx` is not a dependency of this repository, only an option for the downstream analysis. The CSV files load equally well into Gephi, igraph or R.
