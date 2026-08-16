# Family 2 full schedule: analysis plan

Written 2026-05-30, **before any Family 2 full-schedule run is
launched**. Pre-registered together with
`memory/experiments/family-2-full/matrix.md`. Purpose: lock the
decision rules in advance so the rules cannot be tuned to
produce a particular outcome. Mirrors
`memory/experiments/family-1-full/analysis-plan.md` on every
threshold; any divergence is recorded explicitly with a reason.

## Inputs

  * `data/family-2-full/master/runs.csv` (one row per completed
    run; columns include the 2026-05-30 addressing-convention
    additions `target_kind` on edges and
    `n_agent_to_agent_directed` on runs).
  * `data/family-2-full/ledger.json` (run status and timing).
  * `data/family-2-full/runs/<run_id>/datasets/edges.csv`
    (per-run target-kind breakdown).

The pilot at `data/family-2-pilot/` is not part of the full-
schedule analysis. The two are kept separate by experiment-root
to preserve pre-registration discipline.

## Per-cell-and-pattern summary

For each `(agent_count, topology, artefact_policy, pattern, task)`
combination with at least one completed run, report:

  * **N** the number of completed runs at this combination.
  * **success_rate** `verifier passed all tests` / N (binary at
    the run level, treating "all tests passed" as success).
  * **wall_time_s** mean and standard deviation.
  * **a2a** total event count: mean and sd of
    `n_agent_to_agent`.
  * **a2a directed**: mean and sd of
    `n_agent_to_agent_directed` (the canonical + alias subset).
  * **a2f, f2a, n_file_nodes**: mean and sd, same as Family 1.
  * **target_kind shares** (canonical, alias, broadcast, role,
    unknown): per-cell, pooled across runs.

Differences from Family 1's per-cell summary:

  * Two a2a means reported per cell (total event count and
    directed subset). The total is the cross-family-comparable
    metric (invariant under the parser-convention change). The
    directed is the addressed-to-a-resolvable-specific-agent
    metric introduced 2026-05-30.
  * `target_kind` share columns are added so the role-name
    addressing signal surfaces in the report.

## Top-up decision rule (pre-registered)

Same rule as Family 1, applied verbatim, with the same two
thresholds:

A `(cell, pattern, task)` combination is flagged for top-up to
**N = 20** after the first N = 10 pass if EITHER of the
following holds:

  * **Outcome precision.** The Wilson 95 per cent confidence
    interval for the cell's success rate at N = 10 has width
    greater than 0.5.
  * **Graph-statistic precision.** The coefficient of variation
    (`sd / mean`) of any of `n_agent_to_agent`,
    `n_agent_to_agent_directed`, `n_agent_to_file` or
    `n_file_to_agent` exceeds 0.5 at N = 10, restricted to
    cells whose mean is at least 1 for the metric in question
    (the mean < 1 refinement is inherited from Family 1's plan,
    2026-05-23).

The structural-CV refinement deferred from Family 1
(`memory/decisions.md` 2026-05-29) is also inherited: it lands
in the end-of-collection refinement pass after both families'
data is on disk.

**Reviewer defence on the same thresholds.** The Family 1 plan
calibrated the 0.5 thresholds to the precision targets (0.5 CI
width gives a meaningful pass / fail on cells with intermediate
success rates; CV = 0.5 corresponds to about 16% relative
standard error of the cell mean at N = 10, which is the
precision threshold below which we are not willing to draw
cell-level inference). The pilot evidence on Family 2 shows
graph-metric magnitudes within the same regime as Family 1
(pilot mean a2a at baseline ≈ 15.7, sd ≈ 6, CV ≈ 0.38, well
below the threshold), so the same thresholds apply by direct
calibration transfer.

## Pre-registered hypotheses

The Family 2 full schedule tests the following hypotheses,
recorded here in their pre-registered form. Each is paired with
the test that will be applied to confirm or refute it. The
pilot evidence informing each hypothesis is cited.

### H1. n² scaling on chained tasks (RQ1)

**Hypothesis.** At `peer / allowed / clean` on
`summarise_transactions`, the mean number of agent-to-agent
messages per run scales close to the square of the agent
count, parallel to the Family 1 finding.

**Test.** Linear regression of `log(n_agent_to_agent_mean)` on
`log(agent_count)` across `n ∈ {2, 4, 8}`; report slope with
95 % CI. The pre-registered prediction is that the slope is
within [1.5, 2.5] (the same interval the Family 1 plan would
have committed to).

**Pilot evidence.** The pilot ran only one rep at n = 2 (the
other two timed out or had the atypical failure), N = 2 at
n = 8 (one timeout), and N = 3 at n = 4, so the slope from
the pilot is not estimable with precision. The full schedule
gives N = 10 per cell.

### H2. Topology shapes a2a distribution (RQ2)

**Hypothesis.** At `n = 4 / allowed / clean` on
`summarise_transactions`, the topology factor predicts whether
non-adjacent agent pairs communicate. Peer chains concentrate
messages on adjacent-step pairs; orchestrator runs add a star
component centred on the coordinator.

**Test.** Pooled across the N = 10 runs at the peer cell and
the N = 10 runs at the orchestrator cell, compare the mean
`n_agent_to_agent_directed` (the addressed-to-a-resolvable-
specific-agent count) by topology. The pre-registered
prediction is no specific direction; we test for a between-
topology difference with Mann-Whitney U, two-sided, BH
corrected against the other directional comparisons in this
plan.

### H3. Topology × conflict interaction (RQ3)

**Hypothesis.** The topology effect on conflict in Family 2
**differs in direction or magnitude** from Family 1. In
Family 1 the orchestrator topology had a verifier-success
advantage on the conflict pattern at n = 4 (the 8/10 versus
5/10 at mandatory). In the Family 2 pilot the direction was
reversed (peer 2/3 vs orchestrator 1/3 at n = 4 allowed
conflicting, N = 3), suggesting the chain structure of
Family 2 may not benefit from designated coordination on
conflict resolution to the same extent.

**Test.** At each `(4, peer or orchestrator, policy, conflicting)`
cell, report success rate with Wilson 95 % CI. The directional
comparison "peer succeeds at conflict more often than
orchestrator at n = 4" is tested with Fisher's exact (one-
sided), BH corrected against the other directional comparisons
in this plan. The pre-registered alternative is **either**
direction (we test both); the pilot points one way at N = 3
but the prediction is for the full schedule data to resolve
which way.

**Reviewer defence on bi-directional pre-registration.** A
one-sided test pre-registered in the direction the pilot
suggests would be cherry-picking. Pre-registering both
directions and letting the full-schedule data decide is the
honest framing.

### H4. Artefact policy reproduces Family 1's pattern (RQ4)

**Hypothesis.** Artefact policy on Family 2 separates
`mandatory` from `forbidden` and `allowed` on the per-cell
distinct-file-paths metric, with `forbidden` and `allowed`
statistically indistinguishable, parallel to the Family 1
finding.

**Test.** Mann-Whitney U on `n_file_nodes` across the N = 90
pooled runs per policy (pooling the three n = 2 topologies
and the three patterns at each policy). BH correction against
the other comparisons. Pre-registered prediction is the same
direction Family 1 showed.

### H5. Cross-family target-kind contrast (graph-level)

**Hypothesis.** At the comparable cell
`(4, peer, allowed, clean)`, Family 2 has a lower
directed-message share (canonical + alias) than Family 1. The
Family 1 directed share at this cell is 96.8 % (already on
disk, fixed). The pre-registered prediction is **at least a
10-percentage-point gap**: Family 2 directed share ≤ 86.8 %.

**Test.** Per-run directed share at the Family 2 cell, N = 10
runs. Compare to the fixed Family 1 value 96.8 %. One-sided
one-sample test on the per-run share with a 10-percentage-point
margin: the prediction is confirmed if the upper bound of the
two-sided 95 % CI of the Family 2 mean is below 0.868. BH
corrected against the other directional comparisons.

**Reviewer defence on the 10-point margin.** The pilot at this
cell showed a directed share of 70.2 % (a 26.6-point gap from
Family 1's 96.8 %). Pre-registering a threshold tighter than
the pilot observation would be cherry-picking. Pre-registering
a 10-point gap creates a test that can fail: if the full
schedule data shows a Family 2 directed share between 86.8 %
and 96.8 %, the prediction is refuted and the cross-family
contrast is judged smaller than the pilot suggested. The
10-point gap is the smallest cross-family effect size we
consider scientifically meaningful for the paper's claim about
addressing-pattern differences between task families.

### H6. Non-local-dependency task shows reduced canonical addressing

**Hypothesis.** The `summarise_transactions_v2` cell at
`(4, peer, allowed, clean)` has a lower canonical-addressing
share than the `summarise_transactions` cell at the same
configuration, by **at least 15 percentage points**.

**Test.** Per-cell pooled canonical share at the v2 cell vs the
`summarise_transactions` cell, N = 10 runs each. Fisher's
exact on the pooled canonical / non-canonical edge counts,
one-sided (v2 < summarise_transactions). The directional
prediction is confirmed if (a) the test reaches `p_BH < 0.05`
**and** (b) the point estimate of (summarise_transactions
canonical share) minus (v2 canonical share) is at least 15
percentage points. Both conditions are required.

**Reviewer defence on the 15-point gap.** The pilot at N = 3
showed 0 % canonical on v2 versus a `summarise_transactions`
baseline of ~45 % canonical, a 45-point gap. Pre-registering a
15-point gap rather than the pilot's 45-point gap creates
genuine space for the prediction to fail: if v2 at N = 10
shows ~35 % canonical (a 10-point gap from baseline), the
prediction is refuted. Using two conditions (significant p plus
a magnitude threshold) prevents the Fisher's-exact test from
"confirming" a tiny effect simply because of the high pooled
edge count at N = 10. The 15-point margin is calibrated to be
larger than the typical between-cell canonical-share variance
in Family 2 (estimated from pilot per-cell shares: sd of
canonical share ≈ 6-8 percentage points within
`summarise_transactions` cells).

### H7. The conflict footprint reproduces (corroborative)

**Hypothesis.** Verifier failures in the conflicting cells
follow the Instance 5 designed footprint: failed runs fail
exactly the two boundary tests
`test_validate_zero_amount_kept` and
`test_end_to_end_zero_amount_record_included`, with all other
tests passing (23 / 25).

**Test.** For each failed verifier run in a `conflicting`
cell, inspect the failing-test set. The pre-registered
prediction is that ≥ 90 % of B2-converged failures match
the exact two-test footprint. Descriptive; no inferential
test (the prediction is about which tests fail, not the
proportion of failures).

**Pilot evidence.** 3 of 3 B2-converged pilot runs matched
the predicted footprint exactly.

## Inferential statistics

  * **Per-cell success-rate inference.** Wilson 95 % CIs for
    the per-cell binary success rate. Cross-cell comparisons
    use Fisher's exact, two-sided unless otherwise pre-
    registered (H3 stays bi-directional; H4 and H5 are
    directional).
  * **Per-cell graph-metric inference.** Mann-Whitney U for
    between-cell comparisons. The Mann-Whitney is robust to
    non-normality and works on the per-run cell-level
    distributions.
  * **Multiple-comparisons correction.** Benjamini-Hochberg
    across all directional comparisons in this plan plus any
    additional descriptive cell-level tests. Adjusted
    significance threshold p_BH < 0.05.

## Outputs

The analysis pipeline writes
`memory/experiments/family-2-full/preliminary.md` each time it
runs. The report contains:

  * Batch state (planned, ok, errored, succeeded, failed
    counts).
  * The per-cell-and-pattern table described above, sorted in
    matrix order (agent count, topology, artefact policy,
    pattern, task).
  * The top-up list: every cell flagged by either rule above,
    with the rule that flagged it.
  * A short list of cells that look surprising relative to the
    pilot (mean a2a or success rate noticeably outside the
    pilot's range).
  * The per-hypothesis result table after all data lands: for
    each H1-H7, the test, the result, and confirm / refute /
    inconclusive.

## Pilot-informed pre-registration: the honest framing

The Family 2 pilot data is on disk before this plan is written.
Pre-registering hypotheses informed by pilot evidence is
standard practice (pilots exist to inform formal hypotheses),
but it creates a reviewer-relevant risk: thresholds set after
seeing pilot data can be tilted to make confirmation likely.
This plan handles the risk explicitly:

  * **H1, H4, H7** are direction-of-replication predictions
    grounded in Family 1's full-schedule findings (not pilot
    findings). They test whether the Family 1 effects transfer
    to Family 2; the predicted direction is the Family 1
    direction and is independent of the pilot.
  * **H2** is bi-directional (no specific prediction).
  * **H3** is bi-directional explicitly because the pilot's
    direction (peer > orchestrator on conflict) is opposite to
    Family 1's full-schedule finding (orchestrator > peer). The
    pre-registered alternative is "either direction"; the full
    schedule data decides.
  * **H5** uses a 10-percentage-point margin between the fixed
    Family 1 value (96.8 %) and the Family 2 prediction
    (≤ 86.8 %). The pilot showed a 26.6-point gap. Setting the
    margin at 10 points creates real space for refutation
    (15.8 points of intermediate gap would refute).
  * **H6** uses two conditions (significant p plus a 15-point
    margin between the two cells' canonical shares). The pilot
    showed a 45-point gap. The 15-point margin is calibrated to
    exceed the typical between-cell variance, ensuring the
    prediction tests a meaningful magnitude rather than the
    bare existence of a difference.

The thresholds and margins are pre-registered and locked at
this date. They will not be tuned to the data; any deviation is
recorded as a separate dated entry.

## What this plan does NOT cover

  * The Family 1 top-up rule's structural-CV refinement.
    Deferred to the end-of-collection refinement pass per
    `memory/decisions.md` 2026-05-29.
  * Cross-family inferential analysis. Belongs in a separate
    end-of-collection analysis plan, written after both
    families' data is on disk and before any cross-family
    inferential test is run.
  * Network-statistics analysis (clustering, modularity,
    centrality, temporal statistics). The parser writes
    `edges.csv` with the data needed; the analysis plan for
    those metrics is separate.

## What changes if this plan changes

Any change to the rules, thresholds, or hypotheses after this
date (2026-05-30) is a deviation from pre-registration.
Recorded as a new dated entry in this document, with the
reason and the date relative to the data collection. The
honest-record convention is the same as in
`memory/experiments/family-1-full/analysis-plan.md`.
