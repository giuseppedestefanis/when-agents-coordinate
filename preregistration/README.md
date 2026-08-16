# Pre-registration

The paper reports eight hypotheses (H1–H8). Six are pre-registered in both
prediction and test (H1 and H4–H8); H2 and H3 carry qualifications, set out
below and in the paper's statistical appendix. This directory holds the
pre-registration records so the commitments can be checked against the analyses
in `scripts/`.

| file | what it registers | committed |
|---|---|---|
| `experiment-2-analysis-plan.md` | H1, H4, H5, H6 (and H3, qualified below) | 2026-05-29, before any Experiment 2 (chained) full-schedule run (see correction below) |
| `scaling-arm-8step-H7.md` | H7 | before the 8-step (`compute_invoices`) arm ran |
| `scaling-arm-16step-H8.md` | H8 | before the 16-step (`process_billing`) arm ran |
| `experiment-1-analysis-plan.md` | the top-up decision only (no hypothesis) | 2026-05-23, before the Experiment 1 full schedule's first 10-rep pass |

**Correction (2026-08-16).** The plan header says "Written 2026-05-30"; the
committing commit is timestamped 2026-05-29 12:18 UTC and the first
full-schedule run began 15:48 UTC that day, so the ordering holds and the
header date is a one-day labelling error. No cell of the pre-registered H1
test (`peer/allowed/clean`) ran before the commit.

**H2 is not fully pre-registered.** The Experiment 1 plan pre-registers only the top-up decision. H2's predicted direction was fixed from the
Experiment 1 pilot, but its Fisher test and its correction set were specified
after the schedule had run, before the inferential analysis. H2's outcome is
reported as null.

**H3 carries a test qualification.** The Experiment 2 plan pre-registers a
within-Experiment-2 Fisher test of peer against orchestrator on the conflicting
split (inconclusive). The cross-experiment interaction the paper mentions
($p = 0.24$) is an exploratory test the plan does not specify.

## Crosswalk: historical plan numbering to the paper's H1–H8

The Experiment 2 plan uses its own internal numbering (H1–H7), which is **not**
the paper's numbering. This table maps every historical plan hypothesis to its
treatment in the paper, so nothing looks silently renumbered or dropped.

| plan hypothesis (Experiment 2 plan) | paper treatment |
|---|---|
| plan H1 — n² scaling on chained tasks | paper **H1** |
| plan H2 — topology shapes the a2a distribution (adjacent vs star) | reported in the leadership discussion (no hub forms) but not carried as a numbered hypothesis |
| plan H3 — topology × conflict interaction | paper **H3** (with the test qualification above) |
| plan H4 — artefact policy reproduces Experiment 1's pattern | paper **H4** |
| plan H5 — cross-family target-kind contrast | paper **H5** |
| plan H6 — non-local-dependency task reduces canonical addressing | paper **H6** |
| plan H7 — the conflict footprint reproduces (corroborative, descriptive) | not carried in the paper's H1–H8 table |

The paper's remaining hypotheses come from outside the Experiment 2 plan:
paper **H2** (a coordinator helps on conflicting tasks) is pilot-informed and
analysis-specified after collection; paper **H7** and **H8** are the eight-step
and sixteen-step scaling-arm commitments in this directory.

## Provenance of the records

The Experiment 2 analysis plan is the committed plan as written. The two
scaling-arm files are design records: their pre-registered decision-rule bodies
are unchanged from the committing commit, but their one-line status headers were
updated after collection to record the outcome (for example the H7 header now
reads `Status: COMPLETE ... DIRECTIONAL`). The pre-registration proof for each is
the commit that landed the decision rule before any run, noted in the file. So these are the committed decision rules with a post-study status line added; the rule bodies are the pre-data commitment.

A few internal cross-references (to `memory/experiments/...` notes, to
`ledger.json`, and to the runner source) point to the full research repository
and are not needed to read the commitments; the decision rules are
self-contained. The released datasets keep the `family-1`/`family-2` directory
labels, which the paper calls Experiment 1 (distributed) and Experiment 2
(chained).
