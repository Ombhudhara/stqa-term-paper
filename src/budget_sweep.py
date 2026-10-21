"""Run paired random/GA experiments over increasing input budgets."""

import argparse
import csv
import math
import statistics
from pathlib import Path

from .coverage_analysis import RESEARCH_TITLE, _generate_charts, write_outputs
from .main import (
    BUGGY_COMMIT,
    FIXED_COMMIT,
    PROJECT_ROOT,
    _run_experiment,
    _validate_checkout,
    _validate_results,
    _verify_bug_reproduction,
    _run_original_test,
)


METHODS = (("random", "Random"), ("ai_guided", "AI-guided GA"))


def _mean(values):
    return statistics.mean(values) if values else 0.0


def _sample_std(values):
    return statistics.stdev(values) if len(values) > 1 else 0.0


def _write_csv(path, rows):
    fieldnames = list(rows[0]) if rows else []
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _read_csv(path):
    with path.open("r", newline="", encoding="utf-8") as source:
        return list(csv.DictReader(source))


def _summarize_budget(budget, run_summaries, coverage_summaries):
    summary_rows = []
    for method, _ in METHODS:
        run_rows = [
            row for row in run_summaries if row["method"] == method
        ]
        coverage_rows = [
            row for row in coverage_summaries if row["method"] == method
        ]
        metric_fields = (
            "fault_exposing_inputs",
            "fault_exposure_rate",
            "buggy_line_coverage_pct",
            "buggy_branch_coverage_pct",
            "generation_overhead_seconds",
            "target_execution_seconds",
            "total_wall_clock_seconds",
        )
        summary = {"budget": budget, "method": method, "runs": len(run_rows)}
        for field in metric_fields:
            if field in (
                "buggy_line_coverage_pct",
                "buggy_branch_coverage_pct",
            ):
                rows = coverage_rows
            else:
                rows = run_rows
            values = [
                float(row[field])
                for row in rows
                if row.get(field) not in (None, "")
                and math.isfinite(float(row[field]))
            ]
            summary[field + "_mean"] = _mean(values)
            summary[field + "_std"] = _sample_std(values)
        summary_rows.append(summary)
    return summary_rows


def _write_sweep_charts(output_dir, summary_rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    graphs_dir = output_dir / "graphs"
    graphs_dir.mkdir(parents=True, exist_ok=True)
    budgets = sorted(set(int(row["budget"]) for row in summary_rows))

    def values(method, field):
        by_budget = {
            int(row["budget"]): float(row[field])
            for row in summary_rows
            if row["method"] == method
        }
        return [by_budget[budget] for budget in budgets]

    def save_chart(fig, filename):
        fig.suptitle(RESEARCH_TITLE, fontsize=10)
        descriptions = {
            "budget_fault_exposure.png": (
                "Each point is the mean percentage of inputs with different "
                "buggy/fixed results.\n"
                "Values are averaged across paired runs at that budget."
            ),
            "budget_coverage.png": (
                "Mean target-function line and branch coverage across runs.\n"
                "Higher percentages mean more of _match_one was exercised."
            ),
            "budget_generation_overhead.png": (
                "Mean time spent generating inputs and updating the GA search.\n"
                "Lower values mean less generation/search time."
            ),
        }
        fig.text(
            0.5,
            0.86,
            descriptions[filename],
            ha="center",
            va="center",
            fontsize=8,
            wrap=True,
        )
        fig.tight_layout(rect=(0, 0, 1, 0.77))
        fig.savefig(output_dir / filename, dpi=160)
        fig.savefig(graphs_dir / filename, dpi=160)
        plt.close(fig)

    fig, axis = plt.subplots(figsize=(8, 5))
    exposure_rates = []
    for method, label in METHODS:
        method_rates = [
            value * 100
            for value in values(method, "fault_exposure_rate_mean")
        ]
        exposure_rates.extend(method_rates)
        axis.plot(
            budgets,
            method_rates,
            marker="o",
            label=label,
        )
    axis.set_xlabel("Generated test inputs per run")
    axis.set_ylabel("Mean fault-exposing inputs (% of generated inputs)")
    axis.set_title("Selected-bug exposure rate at each test budget")
    axis.set_xticks(budgets)
    axis.set_ylim(0, max(5.0, min(100.0, max(exposure_rates) * 1.25)))
    axis.legend()
    save_chart(fig, "budget_fault_exposure.png")

    fig, axis = plt.subplots(figsize=(8, 5))
    for method, label in METHODS:
        axis.plot(
            budgets,
            values(method, "buggy_line_coverage_pct_mean"),
            marker="o",
            label=label + " line",
        )
        axis.plot(
            budgets,
            values(method, "buggy_branch_coverage_pct_mean"),
            marker=".",
            linestyle="--",
            label=label + " branch",
        )
    axis.set_xlabel("Generated test inputs per run")
    axis.set_ylabel("Mean target-function coverage across runs (%)")
    axis.set_title("Line and branch coverage at each test budget")
    axis.set_xticks(budgets)
    axis.set_ylim(0, 100)
    axis.legend()
    save_chart(fig, "budget_coverage.png")

    fig, axis = plt.subplots(figsize=(8, 5))
    for method, label in METHODS:
        axis.plot(
            budgets,
            values(method, "generation_overhead_seconds_mean"),
            marker="o",
            label=label,
        )
    axis.set_xlabel("Generated test inputs per run")
    axis.set_ylabel("Mean generation/search time per run (seconds)")
    axis.set_title("Input generation overhead at each test budget")
    axis.set_xticks(budgets)
    axis.set_ylim(bottom=0)
    axis.legend()
    save_chart(fig, "budget_generation_overhead.png")


def build_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Compare random and AI-guided testing over input budgets "
            "from 10 through 100."
        )
    )
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--start-budget", type=int, default=10)
    parser.add_argument("--end-budget", type=int, default=100)
    parser.add_argument("--step", type=int, default=10)
    parser.add_argument("--seed", type=int, default=20261021)
    parser.add_argument("--population-size", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument(
        "--buggy-source",
        type=Path,
        default=PROJECT_ROOT / "target_program" / "buggy_source",
    )
    parser.add_argument(
        "--fixed-source",
        type=Path,
        default=PROJECT_ROOT / "target_program" / "fixed_source",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "results",
    )
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.runs < 1 or args.start_budget < 1 or args.step < 1:
        raise SystemExit("--runs, --start-budget, and --step must be positive")
    if args.end_budget < args.start_budget:
        raise SystemExit("--end-budget must be at least --start-budget")
    if args.population_size < 2:
        raise SystemExit("--population-size must be at least 2")
    if args.timeout <= 0:
        raise SystemExit("--timeout must be greater than zero")

    budgets = list(range(args.start_budget, args.end_budget + 1, args.step))
    output_dir = args.output_dir
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    budget_data_dir = output_dir / "budget_sweep"
    budget_data_dir.mkdir(parents=True, exist_ok=True)

    buggy_path, _ = _validate_checkout(
        args.buggy_source,
        BUGGY_COMMIT,
        "Buggy",
    )
    fixed_path, _ = _validate_checkout(
        args.fixed_source,
        FIXED_COMMIT,
        "Fixed",
    )
    _run_original_test(buggy_path, "buggy")
    _run_original_test(fixed_path, "fixed")
    _verify_bug_reproduction(buggy_path, fixed_path, args.timeout)

    all_summaries = []
    for budget in budgets:
        budget_dir = budget_data_dir / ("budget_%d" % budget)
        all_results_path = budget_dir / "all_results.csv"
        expected_rows = 2 * args.runs * budget
        if all_results_path.is_file():
            existing_rows = _read_csv(all_results_path)
            if len(existing_rows) == expected_rows:
                _validate_results(budget_dir, budget, args.runs)
                _generate_charts(str(budget_dir))
                run_summaries = _read_csv(budget_dir / "run_summary.csv")
                coverage_summaries = _read_csv(
                    budget_dir / "coverage_summary.csv"
                )
                print(
                    "\n=== Budget: %d inputs per method/run (reusing %d "
                    "verified observations) ==="
                    % (budget, expected_rows)
                )
                all_summaries.extend(
                    _summarize_budget(
                        budget,
                        run_summaries,
                        coverage_summaries,
                    )
                )
                continue

        print("\n=== Budget: %d inputs per method/run ===" % budget)
        observations, run_metadata = _run_experiment(
            runs=args.runs,
            budget=budget,
            base_seed=args.seed,
            buggy_path=buggy_path,
            fixed_path=fixed_path,
            timeout=args.timeout,
            population_size=args.population_size,
        )
        budget_dir.mkdir(parents=True, exist_ok=True)
        run_summaries, coverage_summaries = write_outputs(
            str(budget_dir),
            observations,
            run_metadata,
        )[:2]
        _validate_results(budget_dir, budget, args.runs)
        all_summaries.extend(
            _summarize_budget(budget, run_summaries, coverage_summaries)
        )

    _write_csv(output_dir / "budget_sweep_summary.csv", all_summaries)
    _write_sweep_charts(output_dir, all_summaries)
    print("\nBudget sweep complete.")
    print("Budgets: %s" % ", ".join(str(budget) for budget in budgets))
    print("Paired seeds per budget: %d" % args.runs)
    print("Summary: %s" % (output_dir / "budget_sweep_summary.csv"))
    print("Charts: %s" % (output_dir / "graphs"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
