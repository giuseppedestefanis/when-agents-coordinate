# Family 1 full schedule, analysis plan

Written 2026-05-23, before the first 10-rep pass has completed. The
purpose of writing this before the data lands is the same as the
purpose of any pre-registered analysis plan: to fix the decision rules
in advance so the rules cannot be tuned to produce a particular
outcome. The rules below are the ones the pipeline in
`scripts/analyse_family1_full.py` applies; if any of them changes after
this date, the change is recorded here with a reason.

## Inputs

  * `data/family-1-full/master/runs.csv` (one row per completed run;
    columns include `run_id`, `cell` parts, `pattern`, `status`,
    `success`, `tests_passed`, `tests_failed`, `wall_time_s`,
    `n_agent_to_agent`, `n_agent_to_file`, `n_file_to_agent`,
    `n_file_nodes`).
  * `data/family-1-full/ledger.json` (run status and timing; used for
    completion checks and error counts).

## Per-cell-and-pattern summary

For each (cell, pattern) combination with at least one completed run,
report:

  * **N** the number of completed runs at this combination.
  * **success_rate** `tests_passed == tests_total` / N.
  * **wall_time_s** mean and standard deviation (run-level wall time).
  * **a2a** mean and standard deviation of `n_agent_to_agent`.
  * **a2f** mean and standard deviation of `n_agent_to_file`.
  * **f2a** mean and standard deviation of `n_file_to_agent`.
  * **n_file_nodes** mean and standard deviation of distinct file paths
    touched.

Counts (a2a, a2f, f2a, n_file_nodes) are read directly from
`runs.csv`. They are write-event and read-event counts respectively
(see `memory/experiments/forbidden-ablation/results.md` for the
distinction between event counts and file counts; this analysis treats
them as event counts and does not derive a "compliance" metric from
them at this stage).

## Top-up decision rule (pre-registered)

A (cell, pattern) combination is flagged for top-up to **N = 20** after
the first **N = 10** pass if EITHER of the following holds:

  * **Outcome precision.** The Wilson 95 per cent confidence interval
    for the cell's success rate at N = 10 has width greater than 0.5.
    At N = 10, the Wilson interval is widest near p = 0.5 (width about
    0.58); it falls below 0.5 outside roughly p < 0.2 or p > 0.8. The
    rule therefore tops up cells whose pilot success rate sits in the
    middle of the unit interval, where the rate is least determined.
  * **Graph-statistic precision.** The coefficient of variation
    `sd / mean` of any of `n_agent_to_agent`, `n_agent_to_file` or
    `n_file_to_agent` exceeds 0.5 at N = 10. CV = 0.5 corresponds to
    a standard error of the mean of 0.5 / sqrt(10) ≈ 0.16, that is
    sixteen per cent relative SE on the cell mean, which is the
    precision threshold below which we are not willing to draw cell-
    level inference. Cells whose CV is below 0.5 already have
    sub-sixteen-per-cent relative precision on the cell mean at
    N = 10 and gain little from N = 20.

The rule combines an outcome-side check and a graph-statistic-side
check because the two RQ groups place different precision demands on
the same data. RQ3 and RQ4 lean on the success-rate estimates;
RQ1 and RQ2 lean on the graph statistics. A cell that is uninteresting
to one group can still be interesting to the other.

Cells whose graph mean is below one for a metric are excluded from
the CV check for that metric. Refinement recorded 2026-05-23, before
any multi-agent cell reached N = 10 in the full schedule. The original
rule excluded only mean == 0 from the CV check, on the formal ground
that CV is undefined at mean zero. The first 43 runs revealed two
solo cells flagged for top-up because `n_file_to_agent` had mean 0.1
and sd 0.3, giving CV = 3.16. The flag is spurious: for any count
metric concentrated near zero, the CV is structurally large
(CV = sqrt((1-p)/p) for a Bernoulli-like variable), and more
repetitions do not reduce it because the metric's variance is bounded
by its mean. The precision check that matters for low-mean counts is
the absolute standard error of the mean (sd/sqrt(N)), which for these
cells is around 0.1 at N = 10 already and does not need topping up.
The principled correction is to restrict the CV rule to metrics that
are consistently non-zero, captured by mean >= 1.

Such a cell is topped up only if it satisfies the outcome rule.

If neither rule holds, the cell stays at N = 10.

### Ghost-row filter (added 2026-05-28, after the full schedule completed)

Rows in `runs.csv` whose `run_id` is not recorded with `status="ok"`
in `ledger.json` are dropped before cell statistics are computed.
This is a defensive check against a contamination mode observed
during the full schedule: a run that errored after a partial
session-file write could have its partial sessions parsed by the
runner's `_finish` step, producing a zero-or-near-zero-count row
in the per-run `datasets/runs.csv` that the master combine then
picked up as if it were a real low-activity run. Mid-batch
preliminary reports were biased low on graph metrics for the
affected cells; the resume mechanism subsequently overwrote each
contaminated cell's datasets with the successful retry's data, so
the final 850/850 master at 2026-05-28 contains zero ghost rows
(verified by the filter dropping zero rows on first invocation).

The fix has two halves. The runner-side half, in
`agent_comms/runner/runner.py`, no longer invokes the parser on
STATUS_ERROR results, so the per-run dataset is never written for
an errored run in the first place. The analysis-side half, in
`scripts/analyse_family1_full.py`, cross-checks every row in
`runs.csv` against the ledger's ok-set before including it in cell
statistics, which catches any historical contamination that
predates the runner fix. Either half on its own is sufficient; both
together are belt-and-braces and audit-friendly.

The filter does not change the top-up decision thresholds. It only
guarantees the rows fed into the decision are runs the ledger
considers ok.

The threshold values (0.5 CI width; 0.5 CV) are recorded here so they
are part of the analysis-plan record. They may not be tuned to the
data. If, after seeing the first pass, the project judges either
threshold to be inappropriate in principle, the change must be
recorded as a separate entry in this file with the justification and
predates the top-up.

## Outputs

The pipeline writes `memory/experiments/family-1-full/preliminary.md`
each time it is run. The report contains:

  * Batch state (planned, ok, errored, succeeded, failed counts).
  * The per-cell-and-pattern table described above, sorted in matrix
    order (agent count, topology, artefact policy, pattern).
  * The top-up list: every cell flagged by either rule above, with the
    rule that flagged it.
  * A short list of cells that look surprising relative to the pilot
    (mean a2a or success rate noticeably outside the pilot's range).
    This is descriptive, not part of the top-up decision.

## What this plan does NOT cover

The full statistical analysis for the paper (per-RQ tests, effect-size
measures, multiple-comparison correction across cells and families) is
not pre-registered here. That work belongs in a separate analysis
plan, written after the top-up pass completes and before any
inferential test is run. The present plan covers only the top-up
decision.

The network statistics derivable from `edges.csv` (clustering,
modularity, centrality, temporal statistics) are not in this plan.
They are computed from the per-run datasets, not from the aggregated
`runs.csv`, and their analysis plan will be written separately.
