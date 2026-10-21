"""CSV summaries, paired comparisons, and plots derived from experiment data."""

import csv
import itertools
import math
import os
import statistics


RESEARCH_TITLE = (
    "Intelligent Test Input Generation Using AI\n"
    "for Improving Random Testing Effectiveness"
)


T_CRITICAL_95 = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571,
    6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
    11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131,
    16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
    21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060,
    26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042,
}


def _write_csv(path, rows, fieldnames=None):
    if fieldnames is None:
        fieldnames = list(rows[0]) if rows else []
    with open(path, "w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(
            output,
            fieldnames=fieldnames,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def _read_csv(path):
    with open(path, "r", newline="", encoding="utf-8") as source:
        return list(csv.DictReader(source))


def _as_bool(value):
    return str(value).strip().lower() in ("true", "1", "yes")


def _json_set(value):
    import json
    return set(tuple(item) if isinstance(item, list) else item
               for item in json.loads(value or "[]"))


def _coverage_for_run(rows, method, run_number, seed):
    result = {
        "method": method,
        "run": run_number,
        "seed": seed,
    }
    for version in ("buggy", "fixed"):
        line_set = set()
        branch_arcs = set()
        total_statements = 0
        total_branches = None
        branch_supported = True
        for row in rows:
            line_set.update(_json_set(row[version + "_coverage_lines"]))
            branch_arcs.update(_json_set(row[version + "_coverage_branch_arcs"]))
            total_statements = max(
                total_statements,
                int(row[version + "_total_statements"] or 0),
            )
            if _as_bool(row[version + "_branch_coverage_supported"]):
                observed_total = row[version + "_total_branches"]
                if observed_total not in (None, ""):
                    total_branches = int(observed_total)
            else:
                branch_supported = False

        line_pct = (
            100.0 * len(line_set) / total_statements
            if total_statements else 0.0
        )
        result[version + "_lines_covered"] = len(line_set)
        result[version + "_lines_total"] = total_statements
        result[version + "_line_coverage_pct"] = line_pct
        result[version + "_branch_coverage_supported"] = branch_supported
        if branch_supported and total_branches is not None:
            result[version + "_branches_covered"] = len(branch_arcs)
            result[version + "_branches_total"] = total_branches
            result[version + "_branch_coverage_pct"] = (
                100.0 * len(branch_arcs) / total_branches
                if total_branches else 0.0
            )
        else:
            result[version + "_branches_covered"] = ""
            result[version + "_branches_total"] = ""
            result[version + "_branch_coverage_pct"] = ""
    return result


def _paired_permutation_p_value(random_values, guided_values):
    pairs = [
        float(guided) - float(baseline)
        for baseline, guided in zip(random_values, guided_values)
        if baseline not in (None, "") and guided not in (None, "")
    ]
    pairs = [value for value in pairs if math.isfinite(value)]
    if not pairs:
        return ""
    observed = abs(sum(pairs) / len(pairs))
    if observed == 0:
        return 1.0
    if len(pairs) <= 16:
        sign_patterns = itertools.product((-1.0, 1.0), repeat=len(pairs))
        values = [
            abs(sum(sign * value for sign, value in zip(pattern, pairs)) / len(pairs))
            for pattern in sign_patterns
        ]
    else:
        import random
        generator = random.Random(8675309)
        values = [
            abs(
                sum(
                    (1.0 if generator.getrandbits(1) else -1.0) * value
                    for value in pairs
                ) / len(pairs)
            )
            for _ in range(100000)
        ]
    extreme = sum(value >= observed - 1e-12 for value in values)
    return float(extreme) / len(values)


def _statistics(values):
    clean = [float(value) for value in values if value not in (None, "")]
    if not clean:
        return {
            "mean": "",
            "median": "",
            "std": "",
            "min": "",
            "max": "",
            "ci95_low": "",
            "ci95_high": "",
        }
    mean = sum(clean) / len(clean)
    median = statistics.median(clean)
    deviation = statistics.stdev(clean) if len(clean) > 1 else 0.0
    if len(clean) > 1:
        critical = T_CRITICAL_95.get(
            len(clean) - 1,
            1.96,
        )
        margin = critical * deviation / math.sqrt(len(clean))
        ci_low = mean - margin
        ci_high = mean + margin
    else:
        ci_low = ""
        ci_high = ""
    return {
        "mean": mean,
        "median": median,
        "std": deviation,
        "min": min(clean),
        "max": max(clean),
        "ci95_low": ci_low,
        "ci95_high": ci_high,
    }


def _make_comparisons(run_summaries):
    metrics = (
        "buggy_line_coverage_pct",
        "buggy_branch_coverage_pct",
        "fault_exposing_inputs",
        "fault_exposure_rate",
        "generation_overhead_seconds",
        "target_execution_seconds",
        "total_wall_clock_seconds",
    )
    result = []
    for metric in metrics:
        by_method = {}
        for method in ("random", "ai_guided"):
            by_method[method] = {
                int(row["run"]): row.get(metric, "")
                for row in run_summaries
                if row["method"] == method
            }
        paired_runs = sorted(
            set(by_method["random"]).intersection(by_method["ai_guided"])
        )
        random_values = [
            by_method["random"][run] for run in paired_runs
        ]
        guided_values = [
            by_method["ai_guided"][run] for run in paired_runs
        ]
        valid_pairs = [
            (random_value, guided_value)
            for random_value, guided_value in zip(random_values, guided_values)
            if random_value not in (None, "") and guided_value not in (None, "")
        ]
        valid_random = [pair[0] for pair in valid_pairs]
        valid_guided = [pair[1] for pair in valid_pairs]
        random_stats = _statistics(random_values)
        guided_stats = _statistics(guided_values)
        result.append({
            "metric": metric,
            "paired_runs": len(valid_pairs),
            "random_mean": random_stats["mean"],
            "random_median": random_stats["median"],
            "random_std": random_stats["std"],
            "random_min": random_stats["min"],
            "random_max": random_stats["max"],
            "random_ci95_low": random_stats["ci95_low"],
            "random_ci95_high": random_stats["ci95_high"],
            "ai_guided_mean": guided_stats["mean"],
            "ai_guided_median": guided_stats["median"],
            "ai_guided_std": guided_stats["std"],
            "ai_guided_min": guided_stats["min"],
            "ai_guided_max": guided_stats["max"],
            "ai_guided_ci95_low": guided_stats["ci95_low"],
            "ai_guided_ci95_high": guided_stats["ci95_high"],
            "mean_difference_ai_minus_random": (
                guided_stats["mean"] - random_stats["mean"]
                if random_stats["mean"] != "" and guided_stats["mean"] != ""
                else ""
            ),
            "paired_permutation_p_value": _paired_permutation_p_value(
                valid_random,
                valid_guided,
            ),
            "comparison_method": (
                "two-sided exact paired sign-flip permutation test"
                if len(valid_pairs) <= 16
                else "two-sided Monte Carlo paired sign-flip test (100000 draws)"
            ),
        })
    return result


def _build_run_summaries(observations, run_metadata):
    summaries = []
    coverages = []
    faults = []
    timings = []
    metadata_by_key = {
        (item["method"], int(item["run"])): item
        for item in run_metadata
    }
    methods_runs = sorted(
        set((row["method"], int(row["run"])) for row in observations)
    )
    for method, run_number in methods_runs:
        rows = [
            row for row in observations
            if row["method"] == method and int(row["run"]) == run_number
        ]
        seed = rows[0]["seed"]
        detected = [
            row for row in rows if _as_bool(row["distinguishes_versions"])
        ]
        distinct_faults = sorted(set(row["fault_id"] for row in detected if row["fault_id"]))
        coverage = _coverage_for_run(rows, method, run_number, seed)
        coverages.append(coverage)

        fault = {
            "method": method,
            "run": run_number,
            "seed": seed,
            "evaluation_inputs": len(rows),
            "target_exception_inputs": sum(
                1 for row in rows
                if not _as_bool(row["buggy_ok"])
                or not _as_bool(row["fixed_ok"])
            ),
            "fault_exposing_inputs": len(detected),
            "fault_exposure_rate": len(detected) / float(len(rows) or 1),
            "distinct_faults_detected": len(distinct_faults),
            "detected_fault_ids": ";".join(distinct_faults),
        }
        faults.append(fault)

        metadata = metadata_by_key.get((method, run_number), {})
        timings.append({
            "method": method,
            "run": run_number,
            "seed": seed,
            "evaluation_inputs": len(rows),
            "target_executions": sum(
                int(row["target_execution_count"]) for row in rows
            ),
            "target_exception_inputs": fault["target_exception_inputs"],
            "generation_overhead_seconds": sum(
                float(row["generation_time_seconds"]) for row in rows
            ),
            "buggy_execution_seconds": sum(
                float(row["buggy_execution_seconds"]) for row in rows
            ),
            "fixed_execution_seconds": sum(
                float(row["fixed_execution_seconds"]) for row in rows
            ),
            "target_execution_seconds": sum(
                float(row["target_execution_seconds"]) for row in rows
            ),
            "pair_roundtrip_seconds": sum(
                float(row["pair_roundtrip_seconds"]) for row in rows
            ),
            "total_wall_clock_seconds": metadata.get(
                "total_wall_clock_seconds", ""
            ),
        })

        summary = {
            "method": method,
            "run": run_number,
            "seed": seed,
            "evaluation_inputs": len(rows),
            "target_executions": sum(
                int(row["target_execution_count"]) for row in rows
            ),
            "target_exception_inputs": fault["target_exception_inputs"],
            "fault_exposing_inputs": len(detected),
            "fault_exposure_rate": len(detected) / float(len(rows) or 1),
            "distinct_faults_detected": len(distinct_faults),
            "generation_overhead_seconds": timings[-1][
                "generation_overhead_seconds"
            ],
            "target_execution_seconds": timings[-1]["target_execution_seconds"],
            "total_wall_clock_seconds": metadata.get(
                "total_wall_clock_seconds", ""
            ),
        }
        for key in (
            "buggy_line_coverage_pct",
            "buggy_branch_coverage_pct",
            "buggy_lines_covered",
            "buggy_lines_total",
            "fixed_line_coverage_pct",
            "fixed_branch_coverage_pct",
        ):
            summary[key] = coverage.get(key, "")
        summaries.append(summary)
    return summaries, coverages, faults, timings


def _mean(values):
    values = [float(value) for value in values if value not in (None, "")]
    return sum(values) / len(values) if values else 0.0


def _generate_charts(output_dir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    coverage = _read_csv(os.path.join(output_dir, "coverage_summary.csv"))
    faults = _read_csv(os.path.join(output_dir, "fault_detection_summary.csv"))
    timings = _read_csv(os.path.join(output_dir, "timing_summary.csv"))
    observations = _read_csv(os.path.join(output_dir, "all_results.csv"))
    graphs_dir = os.path.join(output_dir, "graphs")
    if not os.path.isdir(graphs_dir):
        os.makedirs(graphs_dir)

    def save_chart(figure, filename, description):
        figure.text(
            0.5,
            0.86,
            description,
            ha="center",
            va="center",
            fontsize=8,
            wrap=True,
        )
        figure.tight_layout(rect=(0, 0, 1, 0.77))
        figure.savefig(os.path.join(output_dir, filename), dpi=160)
        figure.savefig(os.path.join(graphs_dir, filename), dpi=160)

    methods = ("random", "ai_guided")

    line_values = {
        method: [
            float(row["buggy_line_coverage_pct"])
            for row in coverage
            if row["method"] == method
        ]
        for method in methods
    }
    branch_values = {
        method: [
            float(row["buggy_branch_coverage_pct"])
            for row in coverage
            if row["method"] == method
            and row["buggy_branch_coverage_pct"] not in ("", "None")
        ]
        for method in methods
    }
    x = [0, 1]
    width = 0.36
    fig, axis = plt.subplots(figsize=(8, 5))
    axis.bar(
        [value - width / 2 for value in x],
        [_mean(line_values[method]) for method in methods],
        width,
        label="Line coverage",
    )
    if any(branch_values.values()):
        axis.bar(
            [value + width / 2 for value in x],
            [_mean(branch_values[method]) for method in methods],
            width,
            label="Branch coverage",
        )
    axis.set_xticks(x)
    axis.set_xticklabels(("Random", "AI-guided GA"))
    axis.set_xlabel("Test input generation method")
    axis.set_ylabel("Mean target-function coverage across runs (%)")
    axis.set_title("Average line and branch coverage")
    axis.set_ylim(0, 100)
    axis.legend()
    fig.suptitle(RESEARCH_TITLE, fontsize=10)
    save_chart(
        fig,
        "coverage_comparison.png",
        "Bars show the mean percentage of executable lines or branch paths\n"
        "reached in _match_one; higher values mean more code was exercised.",
    )
    plt.close(fig)

    fig, axis = plt.subplots(figsize=(8, 5))
    fault_rates = [
        _mean([
            row["fault_exposure_rate"] for row in faults
            if row["method"] == method
        ]) * 100
        for method in methods
    ]
    axis.bar(("Random", "AI-guided GA"), fault_rates, color=("#5B8FF9", "#61DDAA"))
    axis.set_xlabel("Test input generation method")
    axis.set_ylabel("Mean fault-exposing inputs (% of generated inputs)")
    axis.set_title("Rate of inputs revealing the selected bug")
    axis.set_ylim(0, max(5.0, min(100.0, max(fault_rates) * 1.25)))
    fig.suptitle(RESEARCH_TITLE, fontsize=10)
    save_chart(
        fig,
        "fault_detection_comparison.png",
        "An input exposes the bug when buggy and fixed versions return "
        "different results.\n"
        "Bars show the mean percentage of inputs exposing this benchmark bug.",
    )
    plt.close(fig)

    def timing_chart(filename, field, title, ylabel, description):
        fig, axis = plt.subplots(figsize=(8, 5))
        values = [
            [
                float(row[field]) for row in timings
                if row["method"] == method and row[field] not in ("", "None")
            ]
            for method in methods
        ]
        axis.bar(("Random", "AI-guided GA"), [_mean(items) for items in values])
        axis.set_xlabel("Test input generation method")
        axis.set_ylabel(ylabel)
        axis.set_title(title)
        fig.suptitle(RESEARCH_TITLE, fontsize=10)
        save_chart(fig, filename, description)
        plt.close(fig)

    timing_chart(
        "generation_overhead_comparison.png",
        "generation_overhead_seconds",
        "Generation and search overhead",
        "Mean generation/search time per method run (seconds)",
        "Mean time spent proposing inputs and updating the GA search\n"
        "across runs; lower values indicate less search overhead.",
    )
    timing_chart(
        "total_runtime_comparison.png",
        "total_wall_clock_seconds",
        "Total elapsed experiment time",
        "Mean total elapsed time per method run (seconds)",
        "Mean end-to-end time, including worker startup, evaluation, and "
        "communication.\n"
        "Lower values indicate a faster run.",
    )

    run_curves = {}
    for method in methods:
        method_runs = sorted(set(
            int(row["run"]) for row in observations if row["method"] == method
        ))
        run_curves[method] = []
        for run_number in method_runs:
            rows = sorted(
                (
                    row for row in observations
                    if row["method"] == method
                    and int(row["run"]) == run_number
                ),
                key=lambda row: int(row["test_index"]),
            )
            seen = set()
            total = int(rows[0]["buggy_total_statements"]) if rows else 0
            curve = []
            for row in rows:
                seen.update(_json_set(row["buggy_coverage_lines"]))
                curve.append(100.0 * len(seen) / total if total else 0.0)
            run_curves[method].append(curve)
    fig, axis = plt.subplots(figsize=(9, 5))
    for method, label in (("random", "Random"), ("ai_guided", "AI-guided GA")):
        curves = run_curves[method]
        if not curves:
            continue
        budget = min(len(curve) for curve in curves)
        means = [
            sum(curve[index] for curve in curves) / len(curves)
            for index in range(budget)
        ]
        axis.plot(range(1, budget + 1), means, label=label)
    axis.set_xlabel("Number of generated test inputs evaluated (per run)")
    axis.set_ylabel("Mean cumulative _match_one line coverage across runs (%)")
    axis.set_title("How line coverage grows as more inputs are tested")
    axis.set_ylim(0, 100)
    axis.legend()
    fig.suptitle(RESEARCH_TITLE, fontsize=10)
    save_chart(
        fig,
        "coverage_progression.png",
        "Each point is mean target-function line coverage after evaluating "
        "that many inputs.\n"
        "A faster increase means new lines were reached earlier.",
    )
    plt.close(fig)


def generate_architecture_diagram(path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

    fig, axis = plt.subplots(figsize=(12, 6))
    axis.set_xlim(0, 12)
    axis.set_ylim(0, 6)
    axis.axis("off")
    boxes = {
        "random": (0.5, 3.6, 2.2, 1.0, "Seeded random\ninput generator"),
        "ga": (0.5, 1.2, 2.2, 1.2, "GA input generator\ncoverage + novelty"),
        "runner": (4.0, 2.5, 2.2, 1.2, "Shared test runner\npaired evaluation"),
        "buggy": (7.5, 3.7, 2.0, 0.9, "Buggy checkout\nBugsInPy Bug 1"),
        "fixed": (7.5, 1.7, 2.0, 0.9, "Fixed checkout\nreference oracle"),
        "outputs": (10.2, 2.5, 1.5, 1.2, "CSV summaries\nand charts"),
    }
    centers = {}
    for key, (x, y, width, height, label) in boxes.items():
        patch = FancyBboxPatch(
            (x, y),
            width,
            height,
            boxstyle="round,pad=0.08",
            linewidth=1.4,
            edgecolor="#25476A",
            facecolor="#EAF2F8",
        )
        axis.add_patch(patch)
        axis.text(x + width / 2, y + height / 2, label,
                  ha="center", va="center", fontsize=9)
        centers[key] = (x + width / 2, y + height / 2)

    def arrow(source, target, color="#425B76", label=None, curve=0.0):
        start = centers[source]
        end = centers[target]
        patch = FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            mutation_scale=13,
            linewidth=1.2,
            color=color,
            connectionstyle="arc3,rad=%s" % curve,
            shrinkA=35,
            shrinkB=35,
        )
        axis.add_patch(patch)
        if label:
            axis.text(
                (start[0] + end[0]) / 2,
                (start[1] + end[1]) / 2 + 0.12,
                label,
                fontsize=8,
                ha="center",
            )

    arrow("random", "runner", label="candidates")
    arrow("ga", "runner", label="candidates")
    arrow("runner", "buggy", label="result + coverage")
    arrow("runner", "fixed", label="evaluation only")
    arrow("buggy", "ga", color="#C0504D", label="fitness feedback", curve=0.22)
    arrow("runner", "outputs", label="observations")
    axis.text(
        6,
        5.35,
        "AI-guided vs. random testing of youtube-dl _match_one",
        ha="center",
        va="center",
        fontsize=13,
        fontweight="bold",
    )
    fig.tight_layout()
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def write_outputs(output_dir, observations, run_metadata):
    if not os.path.isdir(output_dir):
        os.makedirs(output_dir)
    random_rows = [row for row in observations if row["method"] == "random"]
    guided_rows = [row for row in observations if row["method"] == "ai_guided"]
    _write_csv(os.path.join(output_dir, "random_results.csv"), random_rows)
    _write_csv(os.path.join(output_dir, "ai_results.csv"), guided_rows)
    _write_csv(os.path.join(output_dir, "all_results.csv"), observations)

    summaries, coverages, faults, timings = _build_run_summaries(
        observations,
        run_metadata,
    )
    _write_csv(os.path.join(output_dir, "run_summary.csv"), summaries)
    _write_csv(os.path.join(output_dir, "coverage_summary.csv"), coverages)
    _write_csv(os.path.join(output_dir, "fault_detection_summary.csv"), faults)
    _write_csv(os.path.join(output_dir, "timing_summary.csv"), timings)
    _write_csv(
        os.path.join(output_dir, "comparison.csv"),
        _make_comparisons(summaries),
    )
    _generate_charts(output_dir)
    return summaries, coverages, faults, timings