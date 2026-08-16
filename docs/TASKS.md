# The task library

Consolidated reference for the runnable tasks (formerly the per-folder READMEs under `tasks/`).


---

## Family 1: distributed knowledge (`tasks/family-1/`)
This directory holds the runnable artefacts for the Family 1 pilot task
instances: the verifier test suites and a reference solution for each distinct
task.

The design source of truth for each instance, including the integrated
specification, the component split, the agent-to-component assignment, the
prompt templates and the expected graph signature, is the corresponding
markdown file in `memory/tasks/family-1/`. The files here are extracted from
those markdown files.

### Layout

```
instance-1/   process_orders, minimum complexity
  verifier.py   test suite (22 tests)
  solution.py   reference implementation
instance-2/   build_report, eight components
  verifier.py   test suite (31 tests)
  solution.py   reference implementation
instance-3/   process_orders, overlapping distribution (reuses instance-1)
  README.md
instance-4/   process_orders without sorting, dependent components
  verifier.py   test suite (20 tests)
  solution.py   reference implementation
instance-5/   process_orders, mild conflict (reuses instance-1)
  README.md
```

Instances 3 and 5 reuse the Instance 1 task without change; they vary only the
distribution of components across agents, which is a property of the prompts
and the assignment; the verifier is unchanged. Instance 4 is a `process_orders`
variant with sorting removed, so it has its own verifier and reference
solution.

### Using a verifier

Each verifier expects a `solution.py` in the same directory exposing the named
function. The reference `solution.py` validates the verifier: the test suite
passes against it. During an experimental run the agent team produces its own
`solution.py` in an isolated working directory, and neither the verifier nor
the reference solution is shown to the agents.

Run a verifier one instance at a time, so that the `solution` module does not
clash between instances:

```
.venv/bin/python -m pytest tasks/family-1/instance-1/verifier.py
```

### Validation status

The verifier of each distinct task passes against its reference solution:

| Instance | Tests | Result |
|----------|-------|--------|
| 1        | 22    | pass   |
| 2        | 31    | pass   |
| 4        | 20    | pass   |
| 3, 5     | 22    | covered by Instance 1 |


---

## Family 1, robustness instance 3
Instance 3 (overlapping distribution) reuses the Instance 1 `process_orders`
task without change. It has no verifier or reference solution of its own.

To run the verifier for an Instance 3 experimental run, use the Instance 1
artefacts:

- `tasks/family-1/instance-1/verifier.py`
- `tasks/family-1/instance-1/solution.py` (reference solution)

Instance 3 differs from Instance 1 only in the agent-to-component assignment
and the agent prompts, documented in `memory/tasks/family-1/instance-3.md`.
Those differences change how the specification is communicated; what a correct implementation must do is unchanged, so the success criterion is the Instance 1
test suite (22 tests).


---

## Family 1, robustness instance 5
Instance 5 (mild conflict) reuses the Instance 1 `process_orders` task without
change. It has no verifier or reference solution of its own.

To run the verifier for an Instance 5 experimental run, use the Instance 1
artefacts:

- `tasks/family-1/instance-1/verifier.py`
- `tasks/family-1/instance-1/solution.py` (reference solution)

Instance 5 differs from Instance 1 only in the agent-to-component assignment
and the agent prompts: the validation component is held by two agents in two
versions that disagree on whether an order with `quantity` equal to `0` is
valid. Version B1 (`quantity > 0`) matches the verifier; version B2
(`quantity >= 0`) does not. The Instance 1 reference solution already
implements B1, so it is the reference solution for Instance 5. The success
criterion is the Instance 1 test suite (22 tests); a team that resolves the
conflict in favour of B2 fails `test_rejects_zero_quantity`.

The conflict is documented in `memory/tasks/family-1/instance-5.md`.


---

## Family 2: sequential dependency (`tasks/family-2/`)
This directory holds the runnable artefacts for the Family 2 pilot task
instances: the verifier test suites and a reference solution for each
distinct task. Family 2 is the sequential-dependency family; each task is a
chain of transformations composed by a `pipeline.py`, so a reference solution is a directory of step modules.

The design source of truth for each instance, including the team-level
signature, the step split, what each agent does and does not know, and the
expected graph signature, is the corresponding markdown file in
`memory/tasks/family-2/`. The forward-committed boundary tests are recorded
in `memory/tasks/family-2/verifier-checklist.md`.

### Layout

```
instance-1/   summarise_transactions (parse, validate, aggregate, format)
  verifier.py        test suite (25 tests)
  solution/          reference pipeline: parse, validate, aggregate,
                     format_output, pipeline
instance-2/   compute_invoices (eight-step chain)
  verifier.py        test suite (31 tests)
  solution/          reference pipeline: parse, validate, resolve_customer,
                     resolve_product, compute_line_totals, apply_discount,
                     compute_tax, format_invoices, pipeline
instance-3/   summarise_transactions, overlapping distribution (reuses instance-1)
  README.md
instance-4/   summarise_transactions_v2 (non-local CATEGORY_ORDER dependency)
  verifier.py        test suite (24 tests)
  solution/          reference pipeline: parse, validate, aggregate,
                     format_output, pipeline
instance-5/   summarise_transactions, mild conflict (reuses instance-1)
  README.md
```

Instances 3 and 5 reuse the Instance 1 task without change; they vary only
the distribution of components across agents, which is a property of the
prompts and the assignment; the verifier is unchanged. Instance 1's verifier is
the binding test contract for Instances 3 and 5 as well (it includes the
zero-amount boundary integration test that discriminates Instance 5's B2
conflict footprint). Instance 2 (`compute_invoices`) and Instance 4
(`summarise_transactions_v2`) are distinct tasks with their own verifiers
and reference pipelines.

### Using a verifier

During an experimental run the runner adds the run's workspace to
`PYTHONPATH`, so the verifier's `from parse import parse` style imports
resolve to the agent team's deliverables. Neither the verifier nor the reference solution is given to the agents or
named in their prompts, and neither is placed in the workspace. They are not
sandboxed away from them either.

To validate a verifier against its reference solution locally, put the
reference directory on `PYTHONPATH` (run one instance at a time so the step
modules do not clash between instances):

```
PYTHONPATH=tasks/family-2/instance-1/solution \
    .venv/bin/python -m pytest tasks/family-2/instance-1/verifier.py
```

Running the verifier without that `PYTHONPATH` raises a collection-time
`ModuleNotFoundError` (no `parse` module), which is expected: the verifier
has no deliverables to test until a workspace or the reference is supplied.

### Validation status

Each verifier passes against its reference solution:

| Instance | Tests | Result |
|----------|-------|--------|
| 1        | 25    | pass   |
| 2        | 31    | pass   |
| 4        | 24    | pass   |
| 3, 5     | 25    | covered by Instance 1 |


---

## Family 2, robustness instance 3
Instance 3 (overlapping distribution) reuses the Instance 1
`summarise_transactions` task without change. It has no verifier
or reference solution of its own.

To run the verifier for an Instance 3 experimental run, use the
Instance 1 artefacts:

- `tasks/family-2/instance-1/verifier.py`
- `tasks/family-2/instance-1/solution/` (reference solution: five
  files implementing the four-step chain plus `pipeline.py`)

Instance 3 differs from Instance 1 only in the agent-to-step
assignment and the agent prompts, documented in
`memory/tasks/family-2/instance-3.md`. The two overlapped steps
(step 2 `validate`, step 3 `aggregate`) are held by two agents
each; the agents must discover the duplication through
coordination and produce one `validate.py` and one `aggregate.py`.
The success criterion is the Instance 1 test suite (25 tests).


---

## Family 2, robustness instance 5
Instance 5 (mild conflict) reuses the Instance 1
`summarise_transactions` task without change. It has no verifier
or reference solution of its own.

To run the verifier for an Instance 5 experimental run, use the
Instance 1 artefacts:

- `tasks/family-2/instance-1/verifier.py`
- `tasks/family-2/instance-1/solution/` (reference solution; the
  reference `validate.py` implements the canonical B1 rule
  `amount >= 0`, so it is the reference solution for Instance 5
  too)

Instance 5 differs from Instance 1 only in the agent-to-step
assignment and the agent prompts: step 2 `validate` is held by
two agents in two versions that disagree on whether a record with
`amount == 0` is valid. Version B1 (`amount >= 0`) matches the
verifier; version B2 (`amount > 0`) does not. The Instance 1
reference solution already implements B1, so it is the reference
for Instance 5.

The success criterion is the Instance 1 test suite (25 tests).
A team that converges on B2 fails `test_validate_zero_amount_kept`
(unit test) and `test_end_to_end_zero_amount_record_included`
(integration test). The two-failing-test footprint matches Family
1 Instance 5's failure mode by design; the integration test was
added to Instance 1's verifier specifically to give Instance 5
this two-test discrimination, and it passes for Instances 1 and 3
because they use the canonical B1 spec (see
`memory/tasks/family-2/verifier-checklist.md` Instance 5 section
for the commitment).

The conflict is documented in
`memory/tasks/family-2/instance-5.md`.
