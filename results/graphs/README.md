# Graph guide

**Study:** Intelligent Test Input Generation Using AI for Improving Random
Testing Effectiveness

The comparison graphs summarize the 10-seed experiment with 200 generated
inputs per method and run. The budget graphs summarize paired experiments at
10, 20, ..., 100 generated inputs per method and run. In each experiment,
every input is run against both the buggy and fixed implementations.

## Comparison graphs

- [`coverage_comparison.png`](./coverage_comparison.png): Mean percentage of
  executable lines and branch paths reached in `youtube_dl.utils._match_one`.
  The x-axis is the input-generation method; the y-axis is target-function
  coverage. Higher values mean more of the function was exercised.
- [`fault_detection_comparison.png`](./fault_detection_comparison.png): Mean
  percentage of generated inputs that returned different results for the
  buggy and fixed versions. The x-axis is the method; the y-axis is the
  selected-bug exposure rate. This benchmark contains one selected bug.
- [`generation_overhead_comparison.png`](./generation_overhead_comparison.png):
  Mean seconds spent generating inputs and updating the genetic search in one
  run. The x-axis is the method; the y-axis is generation/search time.
- [`total_runtime_comparison.png`](./total_runtime_comparison.png): Mean
  end-to-end seconds per method run, including worker startup, evaluation, and
  inter-process communication. The x-axis is the method; the y-axis is elapsed
  time.
- [`coverage_progression.png`](./coverage_progression.png): Mean cumulative
  target-function line coverage as each run evaluates more inputs. The x-axis
  is the number of generated inputs evaluated; the y-axis is the percentage of
  target lines reached so far.

## Input-budget sweep graphs

- [`budget_fault_exposure.png`](./budget_fault_exposure.png): Mean percentage
  of inputs exposing the selected bug for each budget. The x-axis is generated
  inputs per method/run; the y-axis is the fault-exposure rate.
- [`budget_coverage.png`](./budget_coverage.png): Mean line and branch coverage
  reached at each input budget. The x-axis is generated inputs per method/run;
  the y-axis is target-function coverage percentage. Solid/dotted line styles
  distinguish line/branch metrics; the legend identifies the method.
- [`budget_generation_overhead.png`](./budget_generation_overhead.png): Mean
  generation and search seconds at each budget. The x-axis is generated inputs
  per method/run; the y-axis is generation/search time.

For every chart, the legend identifies the plotted method or coverage metric.
Percentages are proportions multiplied by 100; time axes use seconds. Budget
summary data is available in [`../budget_sweep_summary.csv`](../budget_sweep_summary.csv).
