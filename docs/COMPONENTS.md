# The infrastructure, component by component

Consolidated reference for the collection infrastructure (formerly the per-folder READMEs). Four components under `agent_comms/`, plus the collection and analysis scripts under `scripts/`. These documents are shared with the research repository: references to `PLAN.md` and to `memory/...` paths point to that repository's design record, outside this package. Where such a document states a design-time parameter (for example, a planned repetition count), the released schedules in `data/` are authoritative; `scripts/verify_claims.py` checks the released counts.


---

## Message protocol (`agent_comms/message_protocol/`)
The message protocol gives agents a typed channel for inter-agent
communication. Routing inter-agent messages through this channel lets the
session parser build the agent-to-agent edges of the communication graph
cleanly, separately from context handoffs.

### Design

The protocol is an MCP server. Each agent in a run launches its own instance
of the server, configured through environment variables with the agent's own
identity and the path to a shared run log. All instances in a run append to
one log.

The server exposes two tools:

- `send_message(to_agent, content)` records a message from the configured
  agent to `to_agent` and makes it available to that recipient.
- `check_messages()` returns the messages addressed to the configured agent
  that it has not yet received.

MCP is request and response, so the server cannot push a message to a
recipient. Delivery is therefore by polling: a recipient calls
`check_messages()` to collect messages addressed to it. Whether and how often
an agent polls is part of the emergent behaviour under study. The graph is
built from the log regardless of polling, because every `send_message` call is
recorded.

### Log format

The run log is a JSON Lines file. Each line is one event. A `send_message`
call appends a `message` event:

```
{"event": "message", "seq": 0, "run": "<run id>", "from": "agent-1",
 "to": "agent-2", "content": "<text>", "bytes": 42, "tokens_estimate": 11,
 "ts": "2026-05-22T10:00:00.000000+00:00"}
```

A `check_messages` call appends a `poll` event:

```
{"event": "poll", "seq": 7, "run": "<run id>", "agent": "agent-2",
 "delivered": 3, "ts": "2026-05-22T10:00:05.000000+00:00"}
```

`seq` is a monotonically increasing integer equal to the event's line index.
`bytes` is the UTF-8 byte length of the content. `tokens_estimate` is a rough
heuristic of about four characters per token; the authoritative token cost for
an edge comes from the Claude Code session log through the session parser.

When a roster of valid agent identifiers is supplied, a message to or from an
identifier outside the roster is still recorded but is flagged with
`unknown_recipient` or `unknown_sender`.

Per-agent read cursors are kept in sidecar files next to the log
(`<log>.cursor-<agent>`). All reads and writes are serialised with an
exclusive file lock (`<log>.lock`), so the several agent processes of one run
do not corrupt the log or miss messages.

### Environment variables

| Variable             | Required | Meaning                                      |
|----------------------|----------|----------------------------------------------|
| `AGENT_COMMS_SELF`   | yes      | the calling agent's identifier, e.g. agent-1 |
| `AGENT_COMMS_LOG`    | yes      | path to the shared run log JSONL file        |
| `AGENT_COMMS_RUN`    | no       | run identifier recorded in every event       |
| `AGENT_COMMS_ROSTER` | no       | comma-separated list of valid identifiers    |

### Launching the server

```
AGENT_COMMS_SELF=agent-1 \
AGENT_COMMS_LOG=/path/to/run/messages.jsonl \
AGENT_COMMS_RUN=run-001 \
AGENT_COMMS_ROSTER=agent-1,agent-2,agent-3,agent-4 \
python -m agent_comms.message_protocol.server
```

The server is wired into a Claude Code agent through that agent's MCP server
configuration. The experiment runner (component 4) sets the environment
variables per agent and per run.

### Files

- `store.py` is the core `MessageStore`. It has no third-party dependencies,
  so it can be tested without an MCP transport.
- `server.py` is the FastMCP server, a thin wrapper around `MessageStore`.

Tests for the core are in `tests/test_message_protocol.py`.

### Fallback

`PLAN.md` notes a fallback should the MCP route prove unreliable: a file-based
message channel with structured headers, parsed after the run. That fallback
is not implemented. It is recorded as an open question in
`memory/open-questions.md`.


---

## Session parser (`agent_comms/parser/`)
The session parser turns the raw record of a run into the heterogeneous
temporal graph defined in `PLAN.md`, and writes that graph as CSV datasets for
downstream network analysis.

### Inputs

- One or more Claude Code session JSONL files, one per agent session in the
  run. Each file has one JSON object per line; the relevant line types are
  `assistant` (a model turn, carrying `message.usage` and `tool_use` blocks)
  and `user` (carrying `tool_result` blocks).
- Optionally, the message protocol JSONL log for the run (component 1).

### Output

Four CSV files per run: `nodes.csv`, `edges.csv`, `turns.csv` and `runs.csv`.
Their columns are described in `data/README.md`. CSV was chosen because it
loads directly into the tools used for network analysis (pandas and networkx,
Gephi, igraph, R) and because a per-edge table plus a per-run table is exactly
what is needed to build networks and to compare runs.

### What becomes an edge

- `Read` tool call: a file-to-agent edge, subtype `read`.
- `Write` tool call: an agent-to-file edge, subtype `create` for the first
  write to a path in the run and `edit` for later writes.
- `Edit` or `NotebookEdit` tool call: an agent-to-file edge, subtype `edit`.
- `Task` tool call: an agent-to-agent edge, subtype `spawn`.
- A `message` event in the message protocol log: an agent-to-agent edge,
  subtype `message`. The message log is the clean source for inter-agent
  messages; when it is supplied, agent-to-agent message edges come only from it; the `send_message` tool calls in the session files are ignored.

`Bash` calls are not turned into file edges. A shell command can touch files
in ways that cannot be attributed reliably from the session log. This is
recorded as a limitation in `memory/open-questions.md`.

### Token attribution

A turn's `output_tokens` are the cost of everything the turn produced. The
`token_cost` on an edge is that turn's output tokens divided equally across
the tool calls made in the turn. This is a coarse attribution and is the same
rule for every tool. For authoritative token analysis, join an edge to
`turns.csv` on `turn_uuid` and use the per-turn `input_tokens`,
`output_tokens`, `cache_read_tokens` and `cache_creation_tokens`. The
`byte_size` on an edge is exact: the UTF-8 size of the content written, edited
or read.

### Sub-agents

Lines flagged `isSidechain` belong to a spawned sub-agent. The parser
attributes their tool calls to a sub-agent node `<agent>/sub` and records a
`spawn` edge for each `Task` call. Distinguishing several distinct sub-agents
within one session, and recursive sub-sub-agents, is approximate in this
version and is tracked as an open question.

### Usage

```python
from agent_comms.parser import parse_run, combine_datasets

graph, turns = parse_run(
    run_id="run-001",
    sessions=[{"agent_id": "agent-1", "path": "agent-1.jsonl"},
              {"agent_id": "agent-2", "path": "agent-2.jsonl"}],
    out_dir="data/runs/run-001",
    message_log="data/runs/run-001/messages.jsonl",
    run_record={"family": "family-1", "instance": "instance-1",
                "agent_count": 2, "topology": "peer",
                "artefact_policy": "allowed", "success": True})

## concatenate many runs into one master dataset
combine_datasets(["data/runs/run-001", "data/runs/run-002"], "data/master")
```

### Files

- `model.py` the graph data model: `Node`, `Edge`, `Turn`, `RunGraph`.
- `sessions.py` extraction of turns and tool calls from one session JSONL.
- `build.py` construction of a `RunGraph` from sessions and the message log.
- `datasets.py` writing the CSV datasets, and combining runs.

Tests are in `tests/test_parser.py`.


---

## Task generator (`agent_comms/task_generator/`)
The task generator produces a run-ready task instance from a structured task
definition and a set of parameters: the agent count and the distribution
pattern. It is the programmatic successor to the hand-written Family 1 pilot.

### Inputs

- A `Task` from the library (`library.py`). A task is a function whose
  specification is split into labelled components.
- An agent count.
- A distribution pattern: `clean`, `overlapping` or `conflicting`.

### Output

An instance directory containing:

- `instance.json`: a manifest with the task identity, the parameters, the
  agent-to-component assignment, and the paths to the verifier and reference
  solution. The experiment runner (component 4) consumes this manifest.
- `prompts/agent-N.txt`: one prompt per agent, parameterised by the components
  that agent holds. The prompt assigns no role, names no other agent and does
  not mention any communication mechanism.

### Distribution patterns

- `clean`: each component is held by exactly one agent.
- `overlapping`: a clean assignment, then chosen components are each given to
  a second agent as an identical copy. The team must detect the duplication.
- `conflicting`: a clean assignment, then chosen components are each given to
  a second agent as a variant version that differs from the canonical one.
  The primary holder keeps the canonical version, which is the one the
  verifier enforces; the team must detect and resolve the conflict.

A conflicting instance can only be generated for a task that defines a variant
for at least one component. In the `process_orders` task the validation
component has a `lenient` variant.

### Component count and agent count

The component count is a property of the task. When the agent count is at
least the component count, each of the first components goes to one agent and
any further agents start empty. When the agent count is below the component
count, components are distributed in contiguous blocks so that each agent
holds two or more. Overlapping and conflicting patterns need at least two
agents.

### Scope

This version operates on a library of tasks. It computes the assignment and
renders the prompts for any agent count and distribution pattern, but it does
not generate novel component specifications. Varying the component count means
adding tasks of different sizes to the library; the `build_report` task (eight
components) is the next intended library entry. Generating specifications from
nothing is recorded as future work in `memory/open-questions.md`.

### Usage

```python
from agent_comms.task_generator import get_task, generate_instance

task = get_task("process_orders")
manifest = generate_instance(
    task, agent_count=4, pattern="conflicting",
    out_dir="data/runs/run-001/instance")
```

### Files

- `model.py` the task data model: `Component`, `Task`.
- `distribution.py` the agent-to-component assignment algorithm.
- `instance.py` prompt rendering and writing the instance directory.
- `library.py` the structured task library.

Tests are in `tests/test_task_generator.py`.


---

## Experiment runner (`agent_comms/runner/`)
The experiment runner orchestrates runs across the configuration matrix. It is
the component that ties the other three together: for each run it generates a
task instance (component 3), launches the agents with the message protocol
(component 1) wired in, runs the verifier, and feeds the session logs to the
parser (component 2).

### The configuration matrix

PLAN.md crosses three axes:

- agent count: 1, 2, 4, 8;
- topology: solo, orchestrator, peer;
- artefact policy: forbidden, allowed, mandatory.

The full cross product is 36 cells. `is_degenerate` in `matrix.py` is the
single documented place where the degeneracy rule lives. It drops the two
classes PLAN.md names: a peer topology with a single agent, and a mandatory
artefact policy with a single agent. Neither has any inter-agent state to
constrain. This leaves 31 cells. `enumerate_cells` returns them.

A run is one cell combined with a task, a Family 1 distribution pattern and a
repetition index. `expand` turns cells into `RunSpec` objects, one per
repetition. `family_1_specs` builds the full Family 1 plan for a task: solo
cells are emitted once with the clean pattern, because a single agent cannot
realise an overlapping or conflicting distribution; multi-agent cells are
emitted once per pattern. PLAN.md sets 20 repetitions per cell.

### What a run does

`ExperimentRunner.run_one` executes one run:

1. `prepare_run` builds an isolated run directory and generates the task
   instance into it.
2. The launcher runs the agents.
3. `run_verifier` runs the task's pytest verifier against the produced
   solution, in a fresh subprocess with the run's workspace on `PYTHONPATH`.
4. The session logs and the message log are passed to the parser, which
   writes the run's CSV datasets.
5. The outcome is written to `result.json` and recorded in the ledger.

`run_all` executes a batch and then concatenates the per-run datasets into the
master datasets. It is resumable: runs already recorded in the ledger with
status `ok` are skipped. A run recorded as `error` is retried on a restart.

### Run directory layout

Each run gets its own directory under `<experiment_root>/runs/`, named by its
`run_id`, so runs do not interfere with one another:

```
<run_id>/
  spec.json        the RunSpec, for traceability
  instance/        the generated task instance (component 3 output)
  prompts/         per-agent prompts, with the artefact-policy clause added
  workspace/       the shared working directory the agents act in
  sessions/        the collected Claude Code session JSONL files
  messages.jsonl   the message protocol log (component 1)
  mcp/             per-agent MCP server configuration files
  verifier/        the verifier, copied outside the workspace
  datasets/        the parser CSV datasets for the run (component 2)
  result.json      the RunResult
```

The verifier is copied into `verifier/` and never placed in `workspace/`, so
it is not part of the tree the agents are asked to work in. This is placement, with no enforcement: the agents run as ordinary processes with file access
and are not confined to `workspace/`, so paths outside it remain reachable.

### The artefact policy

The artefact policy axis is an intervention (RQ4). The policy is communicated
to the agents by a clause appended to each prompt: `forbidden` allows only the
deliverable file in the shared directory, `mandatory` requires inter-agent
information to pass through shared files, and `allowed` is the unconstrained
baseline and adds no clause. The prompts otherwise name no communication
mechanism, so coordination strategy stays emergent. Enforcing the policy by restricting tools is recorded as an open question.

### The launcher

The step that invokes Claude Code is held behind a pluggable launcher, so the
orchestration can be tested without it. A launcher is any callable:

```
launcher(layout, spec) -> LaunchOutcome
```

It runs the agents (each acting in `layout.workspace_dir`, given its prompt
and, for a multi-agent run, its MCP configuration) and returns a
`LaunchOutcome` listing the session JSONL files produced.

`ClaudeCodeLauncher` in `launch.py` is the production launcher. It drives the
headless `claude` command line, one process per agent, for all three
topologies:

- **solo**: at one agent (the n=1 baseline) a single `claude` process with no
  message protocol. At two or more agents the solo label is wired identically
  to **peer** (one process per agent, each with its own message protocol MCP
  server and `--strict-mcp-config`) and serves as the second flat draw / the
  same-configuration reliability probe; the no-message-protocol case is the
  n=1 baseline only.
- **peer**: one `claude` process per agent, all started together so the agents
  coordinate in real time, each with its own message protocol MCP server and
  `--strict-mcp-config` so the run sees only that server.
- **orchestrator**: realised as designated-coordinator peers. It runs exactly
  like the peer topology; the difference is that `prepare_run` adds a
  coordinator-role clause to the first agent's prompt. This keeps knowledge
  genuinely distributed (each worker process still receives only its own
  components) while designating a hub, which is the RQ4 intervention.

Each agent is launched with a fresh `--session-id`; the launcher then locates
the session JSONL Claude Code writes under `~/.claude/projects/` by globbing
for that id, and copies it into the run's `sessions/` directory so the run
directory is self-contained.

### Authentication: the Claude subscription (no API key)

By default the launcher runs `claude` on the Claude subscription (plan), with no metered API key. It removes `ANTHROPIC_API_KEY` and the third-party provider
variables (`CLAUDE_CODE_USE_BEDROCK`, `CLAUDE_CODE_USE_VERTEX`,
`CLAUDE_CODE_USE_FOUNDRY`) from the environment passed to each `claude`
process, so Claude Code authenticates with the subscription credentials in its
own credential store.

The machine must be signed in to Claude Code with a Claude subscription before
a run. For unattended runs, `claude setup-token` creates a long-lived
subscription token. The plan has usage limits, so the full schedule may need
pacing; the pilot is within reach. Pass `use_subscription=False` to
`ClaudeCodeLauncher` to keep the inherited environment for anyone who does want
API-key billing.

`ClaudeCodeLauncher` is not run by the test suite; `scripts/smoke_run.py` runs
one Family 1 run end to end against the real `claude` as a manual check.

### Files

- `model.py` the matrix cell, run specification and run result data model.
- `matrix.py` the configuration matrix and its expansion into runs.
- `workspace.py` per-run working directory setup, prompts and MCP config.
- `verify.py` running the verifier for a finished run.
- `ledger.py` the resumable record of executed runs.
- `runner.py` the `ExperimentRunner` orchestrator and the launcher contract.
- `launch.py` `ClaudeCodeLauncher`, the production launcher for solo and peer.

Tests are in `tests/test_runner.py` (orchestration, with a fake launcher) and
`tests/test_launch.py` (the launcher, with a fake `claude` executable).


---

## Collection and analysis scripts (`scripts/`)
Helper scripts for the project. They are part of the replication package.

### smoke_run.py

Runs a single Family 1 run end to end through the experiment runner: instance
generation, agent launch with the message protocol, the verifier, and the
parser. It invokes the real `claude` command line. By default it runs on the
**Claude subscription plan** (the launcher strips `ANTHROPIC_API_KEY` so
`claude` authenticates with the subscription only); the
machine must be signed in to Claude Code with a Claude subscription. It is a
manual check and is not part of the automated test suite (`pytest`).

```
.venv/bin/python scripts/smoke_run.py --model claude-opus-4-7
```

Options select the matrix cell (agent count, topology, artefact policy) and
the Family 1 distribution pattern; see `--help`. The run output, including the
CSV datasets, is written under the experiment root (`data/smoke-run/` by
default).

This script is the end-to-end validation PLAN.md asks for before the full
schedule: after a peer run, inspect `<run directory>/messages.jsonl` to confirm
the agents used the message tool, and `<run directory>/datasets/edges.csv` for
the communication graph.

### run_pilot.py

Runs the Family 1 broader pilot batch: 36 runs of the `process_orders` task in
a one-factor-at-a-time design around a four-agent baseline (artefact policy,
distribution pattern and agent count each varied), 3 repetitions per cell.

```
.venv/bin/python scripts/run_pilot.py
```

Like `smoke_run.py` it runs on the Claude subscription plan. The batch is
sequential and takes a few hours and is **resumable**: if it is interrupted, running it again skips the runs already recorded as complete. The default
model is `claude-sonnet-4-6` (light on the subscription's usage limits);
`--model` pins a different one. Output, including the per-run datasets and the
combined `master/` datasets, is written under `data/family-1-pilot/`.

### analyse_pilot.py

Reads `data/family-1-pilot/master/runs.csv`, prints a per-cell summary of
success rates and graph edge counts, and re-runs the verifier against each
verifier-failed run's saved `solution.py` to identify which tests failed.

```
.venv/bin/python scripts/analyse_pilot.py
```

The per-run re-run uses the run's own copied `verifier/verifier.py` (not the
canonical one), so the reference solution at `tasks/family-1/instance-1/`
cannot shadow the agents' `solution.py` on `sys.path`. The full output of the
broader pilot is in `memory/experiments/family-1-broader-pilot/`.

### run_ablation.py

Runs the forbidden-policy enforcement ablation: three repetitions of the
peer / 4 agents / clean / forbidden cell with the workspace directory
filesystem-locked (mode `0o555`, `solution.py` pre-created writable), so
agents cannot create any file other than the deliverable. Compared against
the instruction-based forbidden runs already in the broader pilot, this tests
whether tool-level enforcement of the forbidden policy materially changes the
emergent graph.

```
.venv/bin/python scripts/run_ablation.py
```

Output goes to `data/family-1-ablation/`. Resumable through the ledger. The
result is documented in `memory/experiments/forbidden-ablation/`.

### analyse_ablation.py

Compares the instruction-based forbidden cell from the pilot against the
tool-restricted forbidden cell from the ablation, side by side. Prints
per-run and mean graph counts, then lists the workspace contents at
end-of-run for every run in both experiment roots so the on-disk compliance
can be read directly.

```
.venv/bin/python scripts/analyse_ablation.py
```

### run_spec_check.py

Three repetitions of the cell that missed the int-vs-float subtlety on
`total` most in the broader pilot (`clean / 4 agents / orchestrator /
forbidden`, which failed two of three pilot runs on
`isinstance(result["total"], float)`). Re-run with the tightened Component A
to confirm the spec fix removes the dominant pilot failure mode before the
full schedule.

```
.venv/bin/python scripts/run_spec_check.py
```

Output goes to `data/family-1-spec-check/`. Resumable through the ledger.
The result: 3 of 3 verifier successes against 1 of 3 in the pilot. The fix
is confirmed; results recorded in
`memory/experiments/family-1-spec-check/results.md`.

### run_family1_full.py

The full Family 1 configuration-matrix schedule. Runs `process_orders`
across every non-degenerate cell (31 cells) and every applicable
distribution pattern (4 solo cells × clean only, 27 multi-agent cells ×
{clean, overlapping, conflicting}, for 85 cell-and-pattern combinations
in total). At the default ten repetitions per combination this is 850
runs.

```
.venv/bin/python scripts/run_family1_full.py
```

The decisions behind the schedule are recorded in `memory/decisions.md`:

  * **N = 10 first, top up high-variance cells to 20** (Bai26 lower
    defensible bound; the staged design pays the σ/√N precision cost
    only where the data shows it is needed). The runner's resumable
    ledger means a top-up is re-running the script with `--start 11`
    and `--only-cell-pattern` on the cells selected for top-up.
  * **No run-level parallelism for now**; the pilot's bottleneck was
    the per-account session limit; wall clock was not the constraint.
  * **Model pinned to claude-sonnet-4-6**, the same model used by the
    pilot and the spec-check.

Like the other scripts, this runs on the Claude subscription plan (the
launcher strips `ANTHROPIC_API_KEY`). The batch is resumable; if a
session limit interrupts it, re-running the script picks up the
remaining specs from the ledger. Output goes to `data/family-1-full/`.

Useful flags:

  * `--reps N` repetitions per combination; default 10.
  * `--start R` first replication number; default 1. Set to 11 for the
    top-up pass on selected cells.
  * `--only-cell-pattern LABEL` restrict to one or more cell-and-pattern
    labels (e.g. `process_orders-clean-a4-orchestrator-forbidden`).
    Repeat the flag to list several. Useful for the top-up step and for
    sanity checks.
  * `--model M`, `--timeout S` model and per-run wall-clock ceiling.

### analyse_family1_full.py

The preliminary analysis pipeline for the full Family 1 schedule. Reads
the per-run datasets under `data/family-1-full/runs/*/datasets/`,
rebuilds the master CSVs, applies the pre-registered top-up decision
rule in `memory/experiments/family-1-full/analysis-plan.md`, and writes
`memory/experiments/family-1-full/preliminary.md`. The script can be
run repeatedly while the batch is in progress; the report is overwritten
each time with whatever data is currently on disk.

```
.venv/bin/python scripts/analyse_family1_full.py
```

The top-up rule and the precision thresholds are fixed in
`analysis-plan.md` (Wilson 95% CI width > 0.5 for outcome; coefficient
of variation > 0.5 on any of a2a, a2f, f2a, restricted to metrics whose
cell mean is at least 1). Any change to the rule is recorded in
`analysis-plan.md` with a justification, never silently in code.
