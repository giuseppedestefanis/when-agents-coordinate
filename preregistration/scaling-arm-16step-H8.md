# H8 16-agent scaling arm — design + PRE-REGISTRATION

Status: PRE-REGISTERED. The analysis plan and decision rule below are fixed
BEFORE any run is collected; the commit that lands this file (with an empty
Results section) is the proof of pre-registration. If results text lands before
this commit, H8 becomes post-hoc.

Mirrors the H7 compute_invoices arm (memory/experiments/compute-invoices-scaling/
design.md). It is the executor's pre-registration; the writer writes the
results section into the paper at the end.

## Scientific question
The Discussion commits to this as the first testable prediction: "a break
between eight and sixteen agents is the first testable prediction, and we leave
this to follow-on work" (the next Zhou et al. cohesive layer near 15). H7 found
messaging growth decelerating past four agents; H8 asks whether a SECOND
deceleration appears between 8 and 16 agents.

Unit-count vs coordination (the rival reading, as in H7): a 16-step chain is
fully decomposed only at n=16, so the unit-count account predicts messaging
keeps growing ~n^2 through 8->16 (beta(8->16) ~ 2, work still decomposing); the
coordination/Dunbar account predicts deceleration before then (beta(8->16) < 2).
The break is read at the n=8 knot, BELOW full decomposition (2 steps/agent at
n=8), so a deceleration there cannot be unit-exhaustion. Structural note: the
16-step chain at n in {4,8,16} is the 2x agent-count shift of the H7 8-step arm
at {2,4,8} (steps/agent 4/2/1 in both), so it also discriminates agent-count
from steps-per-agent against H7.

## Run plan
Task:         process_billing (Family 2, Instance 6, 16-step chain).
              Reference + verifier: tasks/family-2/instance-6/ (verifier 41/41
              on the reference; full end-to-end run validated, see task-design.md).
Break test:   peer/allowed/clean, n in {4, 8, 16}, N=20/cell = 60 runs.
Linearisation: peer/mandatory/clean, n=16, N=10 = 10 runs.
Total:        70 fresh runs, ALL in one logical batch (one ledger).
Order:        INTERLEAVED round-robin (scripts/run_h8_scaling.py build_specs):
              each round emits one rep of n=4/8/16 allowed (+ n=16 mandatory for
              the first 10 rounds). The allowed slope cells are balanced at every
              round boundary, so incremental --max-runs collection does not
              confound agent count with session. The n=16 mandatory runs are
              interleaved with the n=16 allowed runs they are compared against.
Data home:    data/h8-16agent/ (own ledger + master/, four-table schema).
Model pin:    claude-sonnet-4-6, recorded per turn in turns.csv.
Runner:       guardian-wrapped; per-run-timeout 2000s, launcher ceiling 1800s
              (n=16 is the heaviest cell; n=8 already hit the old 1000s cap, so
              the ceiling is raised -- tune after the calibration run).
N=20 (not 10): H7 at N=10 was power-limited (Delta=1.10, 95% CI [-0.01, 2.21],
              spanning zero). N=20 is the paper's pre-registered top-up
              threshold for variance-threatened cells; a segment-slope estimate
              is exactly that case. Fallback if cost forces it: N=10 x {4,8,16}
              = 30 runs, written up as directional, not confirmatory.

## PRE-REGISTERED analysis (fixed before data)
Primary: piecewise log-log regression of per-run a2a (n_agent_to_agent) on agent
count, knot at n=8. Per-run OLS of log(a2a) on log(n) within each segment, 95%
CI (the estimator shared with analyse_handshake_timing / analyse_channel_scaling;
slope is base-invariant). Report:
  beta(4->8)   slope over n in {4,8}
  beta(8->16)  slope over n in {8,16}
  Delta = beta(4->8) - beta(8->16), with 95% CI.
Filter total_output_tokens > 0; peer/allowed/clean only; never pool draws (this
arm is peer-only).

Decision rule:
  (a) Delta 95% CI excludes zero on the POSITIVE side  -> a second break is
      present; H8 CONFIRMED.
  (b) beta(8->16) 95% CI contains ~2.0 AND Delta centred near zero -> no further
      break (messaging keeps ~quadratic; unit-count-consistent).
  (c) neither -> DIRECTIONAL / power-limited (report as such, not confirmatory).

Secondary battery (reuse the committed RQ1 scripts, pointed at data/h8-16agent):
  - handshake vs sustained degree: does the quadratic stay an early one-off
    introduction layer (directed tau90 early), and does sustained per-agent
    directed degree stay BELOW the clique (n-1=15) at 16? (analyse_handshake_
    timing / analyse_messaging_structure conventions: directed=canonical+alias,
    self + out-of-roster excluded.)
  - disparity-filter backbone: still no hub at 16 (near-empty backbone)?
  - n=16 mandatory: total coordination-edge exponent C and its token-cost
    analogue vs the n=16 allowed cell -- does mandating files still pull toward
    linear at 16? (analyse_channel_scaling conventions.)

## Reliability caveat (record in the write-up)
A single 70-run batch removes the cross-session confound only if collected in
one sitting; it still measures ONE session. The paper's sharpest reliability
finding is that the Family-1 exponent swings 1.76-2.44 between sessions, so a
16-agent break established here is not shown to be session-independent --
establishing that needs a REPLICATE batch (the same limitation compute_invoices
carries). Do not write 70 runs up as settling the prediction.

Expected property: the chain is all-or-nothing (16 step deliverables +
pipeline.py); one missing deliverable fails the verifier, so the n=16
verifier-SUCCESS rate will likely be lower than n=4/8. This does NOT affect the
PRIMARY metric (a2a messaging is read from the message log regardless of
verifier outcome); it is a secondary observation.

## Results
[EMPTY — to be filled after collection. This empty section + the commit
timestamp are the pre-registration proof.]
