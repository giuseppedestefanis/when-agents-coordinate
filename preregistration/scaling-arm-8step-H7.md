# H7 compute_invoices scaling arm — design record
# Status: COMPLETE (2026-06-10). 30/30 ok. Verdict: DIRECTIONAL (outcome (c)).
# Results: results.md. n=8 finding: n8-rounding-finding.md.
# Pre-commitment commit dfad8a0 landed before any runs (block satisfied).

---

## Scientific question

Does the n=4 segment break in the RQ1 a2a scaling curve reflect a
task-structure artefact (break tracks unit count / full-decomposition
point) or a genuine coordination property (break appears at n=4
regardless of chain length)?

The two existing families cannot separate these explanations:
- F1 (process_orders): 4 components → full decomposition at n=4
- F2 (summarise_transactions): 4 chain steps → full decomposition at n=4
- Both coincide at n=4, so neither is discriminating

compute_invoices (8 chain steps) provides the test:
- At n=4: each agent holds 2 steps — NOT fully decomposed
- At n=8: each agent holds 1 step — fully decomposed
- If break tracks unit count: no break at n=4, break shifts towards n=8
- If break is a coordination property: break appears at n=4 as in F1/F2

---

## Run plan

Task:        compute_invoices (Family 2, Instance 2, 8-step chain)
Cell:        peer / allowed / clean
Agent counts: n ∈ {2, 4, 8}
N per cell:   10
Total runs:   30 (ALL fresh — see rationale below)
Data home:   data/compute-invoices-scaling/  (separate ledger and master)
Model pin:   claude-sonnet-4-6 (recorded per turn in turns.csv)
Runner:      guardian-wrapped, same pattern as F2 full schedule

Rationale for 30 fresh (not reusing existing n=4):
  The existing 10 n=4 runs in data/family-2-full/master/ were collected
  in a different batch (the F2 full schedule). The pilot-vs-full shift at
  F1 n=8 (U=28, p=0.034; mean 121.3 vs 71.3) demonstrates that batches at
  the same pinned model identifier can be statistically distinguishable.
  Mixing an old batch (n=4) with a new batch (n=2, n=8) on exactly the
  two segment endpoints being compared would contaminate the slope
  estimates. All 30 runs in one batch, one ledger.

The existing 10 n=4 runs become a FREE CROSS-BATCH STABILITY CHECK:
  Mann-Whitney (old n=4 batch vs new n=4 batch). Report in §5.1 alongside
  the H7 result. This is the same comparison already in §5.1 for F1.

---

## Pre-registration text (goes in paper BEFORE batch launches)

The following three text changes must be committed to the repo with an
empty Result: field before the executor runs any of the 30 new runs.
The commit timestamp is the proof of pre-registration. If text lands
after runs, H7 becomes post-hoc analysis dressed as pre-registered.

### §4.2 H7 entry (adapt to match H1–H6 register)

H7 (compute_invoices scaling arm, post-hoc extension in response to
review):

Statement: If the n=4 segment break is a coordination property, it will
appear at n=4 for compute_invoices as it does for the two existing
families. If the break tracks task unit count, it will not appear at n=4
for compute_invoices (each agent holds 2 steps at n=4, full decomposition
is at n=8).

Test: piecewise log-log regression of per-run a2a on agent count, knot
fixed at n=4, over all 30 runs. Yields β(2→4), β(4→8), and
Δ = β(2→4) − β(4→8), each with 95% CI.

Decision rule:
  (a) Δ CI excludes 0 positive → break at n=4 despite 8 units
      → coordination property → H7 confirmed
  (b) β(4→8) CI contains 2.0 AND Δ CI centred near 0 → no deceleration
      at n=4 → unit-count tracking → H7 refuted
  (c) Neither → directional; report Δ against reference range [1.32, 1.70]
      from existing families; note N=10/cell is insufficient to distinguish

Power caveat: at N=10/cell, Δ ≈ 0.90 (F1 magnitude) is detectable;
Δ ≈ 0.44 (F2 magnitude) likely is not. Middle result pre-committed to (c).

Reporting location: §5.1, one paragraph; optionally one panel in Figure 3.

Result: [pending]

### §5.1 placeholder paragraph

After the existing F1/F2 scaling comparison:

"To test whether the n=4 break is a coordination property or a
task-structure artefact, we ran compute_invoices — an 8-step chain in
which full decomposition is achieved at n=8, not n=4 — at peer/allowed/
clean, n ∈ {2, 4, 8}, N=10 per cell (H7, §4.2). At n=4 each agent holds
two steps; at n=8 each holds one. compute_invoices at n=8 is also the only
n=8 cell in the study with no structurally idle agents (§8). [Result
pending]"

### §8 idle-agent limitation sentence

"At n=8, both the Family 1 task (process_orders, 4 components) and the
Family 2 main task (summarise_transactions, 4 chain steps) assign work to
only four of the eight agents; the remaining four receive no component and
are structurally idle. This idle-agent structure is a candidate mechanism
for the unit-count hypothesis (the break occurring because team size
exceeds work units at n=4), and means the n=8 cells in both families
cannot cleanly separate coordination load from team-size effects. The
compute_invoices scaling arm (H7) is the only n=8 condition in the study
with no idle agents."

---

## Analysis spec

Script location (to be written): scripts/analyse_compute_invoices_scaling.py
Inputs:
  - data/compute-invoices-scaling/master/runs.csv  (30 new runs)
  - data/family-2-full/master/runs.csv filtered to compute_invoices n=4
    (10 old runs, stability check only — NOT included in the H7 regression)

Output (committed alongside data):
  - Per-cell a2a means at n=2, n=4, n=8 (new batch)
  - Log-log regression slope over all 30 per-run values, 95% CI
  - Piecewise log-log regression: β(2→4), β(4→8), Δ with 95% CIs
  - Two-point segment descriptors: n=2→4 ratio and n=4→8 ratio
  - Mann-Whitney stability check: old vs new n=4 (one sentence)
  - Verifier success rates

Reference values for decision rule:
  F1 n=4→8 log-log slope: 1.32
  F2 n=4→8 log-log slope: 1.70
  n² (no-break) prediction: 2.00
  F1 Δ (β2→4 − β4→8): 0.90
  F2 Δ: 0.44

---

## Idle-agent fact (verified from code 2026-06-09)

summarise_transactions: 4 distributable components (parse, validate,
  aggregate, format_output). The 5th file in solo runs (pipeline.py) is the
  integration entry point (Task.solution_path), NOT a distributable component.
  clean_partition(4, 8) → agents 1–4 hold 1 step each, agents 5–8 idle.
  4/8 idle at n=8.

process_orders (F1): also 4 components. Same partition. 4/8 idle at n=8.

compute_invoices: 8 components. clean_partition(8, 8) → 1 step per agent.
  0/8 idle at n=8. THE ONLY n=8 CELL IN THE STUDY WITH NO IDLE AGENTS.

---

## Blocker check on recovery

Before launching the batch, verify:
  1. git log shows a commit with H7 text BEFORE any runs in
     data/compute-invoices-scaling/ exist
  2. pgrep -fl "compute_invoices" returns nothing (no batch already running)
  3. The new directory data/compute-invoices-scaling/ exists with a ledger
