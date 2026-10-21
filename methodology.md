# Experimental Methodology

## Research questions

1. Under the same number of evaluated inputs, does GA-guided generation cover
   more executable lines or branches in `_match_one()` than seeded random
   generation?
2. How many generated inputs distinguish BugsInPy Bug 1's buggy and fixed
   implementations?
3. What generation overhead and total wall-clock time does each method incur?

The conclusions apply to this single selected bug and input domain; they do not
establish general effectiveness across other programs or faults.

## Target and reproducibility

The target is `_match_one(filter_part, dct)` from BugsInPy's `youtube-dl` Bug 1.
The runner verifies the expected Git commits before execution:

- Buggy commit: `99036a1298089068dcf80c0985bfcc3f8c24f281`
- Fixed commit: `1cc47c667419e0eadc0a6989256ab7b276852adf`

The known regression trigger is `filter_part="is_live"` with
`dct={"is_live": false}`. The buggy version treats every non-`None` value as
present, while the fixed version requires a boolean value to be `true` for the
positive unary filter. The fixed-side implementation is an evaluation oracle,
not a GA fitness input.

Each checkout is imported in its own fresh Python subprocess. This isolates
`sys.modules` and verifies the resolved `youtube_dl.utils` path is beneath the
requested source root. Each process uses JSON-lines input/output, catches target
exceptions, measures function execution time, and records coverage of the
`_match_one()` source range. Python module-level coverage outside the target
function is excluded from the coverage denominator. Coverage contexts separate
per-input observations while the worker keeps one collector active. The
configured timeout applies to each target request; worker startup is allowed up
to 60 seconds because interpreter and source-analysis initialization is outside
the measured target execution.

## Input domain and random baseline

Inputs are valid structured pairs consisting of a filter expression and a
dictionary. The generator covers unary presence/absence checks, numeric
comparisons, and quoted string comparisons. Values include booleans, `None`,
missing keys, empty and non-empty strings, zero, and comparison boundaries
around `0`, `1`, `10`, `100`, `101`, and `1024`. The finite domain is deduplicated
by canonical serialized input. Random generation uses a recorded Python
`random.Random` seed and does not inspect target behavior.

## GA and fitness

The GA maintains a population of structured candidates, uses 3-way tournament
selection, same-kind crossover, and mutation of candidate fields. It rejects
duplicate serialized inputs and generates a fresh candidate when breeding
collides with one already evaluated. The configured population size defaults to
10; mutation probability defaults to 0.8. Each candidate is evaluated once.

For candidate \(x\), fitness is:

\[
F(x) = 10\,A_{\mathrm{new}}(x) +
       2\,L_{\mathrm{new}}(x) +
       3\,B_{\mathrm{new}}(x)
\]

where \(A_{\mathrm{new}}\) is the number of previously unseen control-flow arcs
within `_match_one()`, \(L_{\mathrm{new}}\) is the number of previously unseen
source lines in that function, and \(B_{\mathrm{new}}\) is 1 if the buggy
implementation's semantic outcome has not previously been observed, otherwise
0. This is marginal novelty against the buggy implementation only. No
buggy-versus-fixed comparison, fixed output, or fault-detection label is passed
to the fitness calculation.

GA fitness uses the buggy-side execution that is already part of the paired
evaluation. It does not make an extra target call. Therefore both methods use
exactly one buggy and one fixed target call per generated input: 100 target
calls per method/run in the 50-input pilot, or 400 per method/run in the
200-input main experiment. The evaluation budget is expressed in generated
inputs, with target-call totals recorded separately.

## Evaluation and metrics

For each generated input, the runner compares return values by type and JSON
value. Exceptions are compared by exception type and normalized message;
timings and memory addresses do not affect semantic comparison. A difference is
between successful return values is an input that exposes the selected Bug 1
fault. Exceptions are recorded for diagnosis but are not counted as fault
detections. The number of fault-exposing inputs and the number of distinct
fault IDs are reported separately. At most one distinct benchmark fault is
represented here.

Coverage is measured on each target invocation and aggregated as the union of
covered lines and branch arcs per method/run. Percentages use executable
statements and branch arcs within the target function. Branch coverage is
reported only if the installed `coverage.py` analysis interface supports it;
otherwise the branch values remain unavailable rather than being inferred.

Generation overhead includes random candidate generation or GA candidate
selection/fitness bookkeeping. Target-function execution is timed independently
inside the worker. Total wall-clock time covers the full method/run, including
worker startup, IPC, and evaluation. These measures answer different questions
and are not added together as if they were disjoint timings.

## Statistical analysis

Runs use the same sequence of seeds for both methods, making the per-seed
results paired. `comparison.csv` reports mean, median, sample standard
deviation, minimum, maximum, and a two-sided 95% confidence interval for each
method. Confidence intervals use Student's \(t\) critical values for up to 30
degrees of freedom and the normal approximation for larger samples.

The paired method comparison is a two-sided sign-flip permutation test on
per-seed differences. For at most 16 pairs all sign assignments are enumerated;
for larger samples 100,000 deterministic Monte Carlo assignments are used. The
test assumes exchangeability of pairwise signs under the null. With the proposed
10 runs, results are descriptive and have limited power; statistical
significance is not treated as proof of general superiority.

## Execution procedure

1. Run the expected benchmark test in both checkouts.
2. Probe the known boolean input and require the buggy/fixed outcomes to differ
   as expected.
3. Run the pilot with two seeds and 50 generated inputs per method/run.
4. Repeat the first pilot seed and compare generated inputs, outcomes, and
   coverage for deterministic reproducibility. Timing values are intentionally
   not compared.
5. If the pilot is valid, run the main experiment with 10 seeds and 200 inputs
   per method/run.
6. Run the budget sweep with the same 10 paired seeds at 10, 20, ..., 100
   generated inputs per method/run. Each budget is a separate experiment; no
   result files from the 200-input main run are overwritten.
7. Write raw observations and summaries to CSV, then build charts by reading
   those actual CSV files. Each comparison chart is saved individually in the
   results directory and in its `graphs/` subdirectory, with the full research
   title shown on the chart.

The budget sweep saves detailed per-budget observations under
`results/budget_sweep/budget_<n>/`, aggregated means and sample standard
deviations in `results/budget_sweep_summary.csv`, and budget-trend figures in
`results/graphs/`. The paired seed set is shared across budgets and methods.

The benchmark's `bug.info` records Python 3.7.0. The local workspace virtual
environment used for current validation is Python 3.12.1, so results are
reproducible in the latter environment but Python 3.7 execution has not been
certified here.
