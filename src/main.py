"""Run reproducible random and genetic-algorithm tests for BugsInPy Bug 1."""

import argparse
import csv
import os
import subprocess
import sys
import time
from pathlib import Path

from .ai_guided_testing import GeneticInputGenerator
# pyrefly: ignore[missing-import]
from .coverage_analysis import generate_architecture_diagram, write_outputs
from .random_testing import RandomInputGenerator, input_from_candidate
from .target_worker import TargetWorker
from .test_runner import TestRunner


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUGGY_COMMIT = "99036a1298089068dcf80c0985bfcc3f8c24f281"
FIXED_COMMIT = "1cc47c667419e0eadc0a6989256ab7b276852adf"
DETERMINISTIC_FIELDS = (
    "method",
    "run",
    "test_index",
    "seed",
    "filter_part",
    "dct_json",
    "buggy_ok",
    "buggy_result_type",
    "buggy_result_json",
    "buggy_exception",
    "fixed_ok",
    "fixed_result_type",
    "fixed_result_json",
    "fixed_exception",
    "distinguishes_versions",
    "buggy_coverage_lines",
    "buggy_coverage_arcs",
    "fixed_coverage_lines",
    "fixed_coverage_arcs",
)


def _git_commit(source_path):
    try:
        return subprocess.check_output(
            ["git", "-C", str(source_path), "rev-parse", "HEAD"],
            stderr=subprocess.STDOUT,
            universal_newlines=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(
            "Unable to verify Git commit for %s: %s" % (source_path, exc)
        )


def _validate_checkout(source_path, expected_commit, label):
    source_path = source_path.resolve()
    if not source_path.is_dir():
        raise RuntimeError("%s source directory is missing: %s" % (label, source_path))
    utils_path = source_path / "youtube_dl" / "utils.py"
    test_path = source_path / "test" / "test_utils.py"
    if not utils_path.is_file() or not test_path.is_file():
        raise RuntimeError(
            "%s checkout must contain youtube_dl/utils.py and test/test_utils.py"
            % label
        )
    actual_commit = _git_commit(source_path)
    if actual_commit != expected_commit:
        raise RuntimeError(
            "%s checkout commit mismatch: expected %s, found %s"
            % (label, expected_commit, actual_commit)
        )
    return source_path, actual_commit


def _run_original_test(source_path, label):
    command = [
        sys.executable,
        "-m",
        "unittest",
        "-q",
        "test.test_utils.TestUtil.test_match_str",
    ]
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    completed = subprocess.run(
        command,
        cwd=str(source_path),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        timeout=120,
    )
    report = (completed.stdout + completed.stderr).strip()
    print("[%s benchmark test] %s" % (
        "PASS" if completed.returncode == 0 else "FAIL",
        label,
    ))
    if report:
        print(report)
    if completed.returncode != 0:
        raise RuntimeError(
            "Original benchmark test failed for %s (exit %s)"
            % (label, completed.returncode)
        )


def _verify_bug_reproduction(buggy_path, fixed_path, timeout):
    probe = {"filter_part": "is_live", "dct": {"is_live": False}}
    with TargetWorker(buggy_path, timeout=timeout) as buggy_worker:
        buggy = buggy_worker.execute(probe)
        print("Buggy worker loaded: %s" % buggy_worker.utils_file)
    with TargetWorker(fixed_path, timeout=timeout) as fixed_worker:
        fixed = fixed_worker.execute(probe)
        print("Fixed worker loaded: %s" % fixed_worker.utils_file)
    if not buggy.get("ok") or not fixed.get("ok"):
        raise RuntimeError(
            "Bug reproduction probe raised unexpectedly: buggy=%r fixed=%r"
            % (buggy, fixed)
        )
    buggy_value = buggy.get("result", {}).get("value")
    fixed_value = fixed.get("result", {}).get("value")
    if buggy_value is not True or fixed_value is not False:
        raise RuntimeError(
            "Expected is_live=False to return True in buggy and False in fixed; "
            "observed buggy=%r fixed=%r" % (buggy_value, fixed_value)
        )
    print(
        "Fault reproduced: is_live=False returns True in buggy and False in fixed."
    )


def _run_one_method(
    method,
    run_number,
    seed,
    budget,
    buggy_path,
    fixed_path,
    timeout,
    population_size,
):
    run_started = time.perf_counter()
    observations = []
    if method == "random":
        generator = RandomInputGenerator(seed)
    elif method == "ai_guided":
        generator = GeneticInputGenerator(
            seed=seed,
            population_size=population_size,
        )
    else:
        raise ValueError("Unsupported test method: %s" % method)

    with TargetWorker(buggy_path, timeout=timeout) as buggy_worker:
        with TargetWorker(fixed_path, timeout=timeout) as fixed_worker:
            runner = TestRunner(buggy_worker, fixed_worker)
            for test_number in range(1, budget + 1):
                generation_started = time.perf_counter()
                candidate = generator.next_candidate()
                generation_seconds = time.perf_counter() - generation_started
                test_input = input_from_candidate(candidate)
                test_input["input_id"] = candidate.identifier()
                row, buggy_observation = runner.evaluate(
                    test_input=test_input,
                    method=method,
                    run_number=run_number,
                    seed=seed,
                    test_number=test_number,
                    generation_seconds=generation_seconds,
                )
                if method == "ai_guided":
                    feedback_seconds = generator.observe_with_overhead(
                        buggy_observation
                    )[1]
                    row["generation_time_seconds"] += feedback_seconds
                observations.append(row)

    elapsed = time.perf_counter() - run_started
    metadata = {
        "method": method,
        "run": run_number,
        "seed": seed,
        "evaluation_inputs": len(observations),
        "target_executions": sum(
            row["target_execution_count"] for row in observations
        ),
        "total_wall_clock_seconds": elapsed,
    }
    return observations, metadata


def _run_experiment(
    runs,
    budget,
    base_seed,
    buggy_path,
    fixed_path,
    timeout,
    population_size,
    report_progress=True,
):
    observations = []
    run_metadata = []
    for run_number in range(1, runs + 1):
        seed = base_seed + run_number - 1
        for method in ("random", "ai_guided"):
            print(
                "Running %s, run %d/%d, seed=%d, budget=%d inputs"
                % (method, run_number, runs, seed, budget)
            )
            rows, metadata = _run_one_method(
                method=method,
                run_number=run_number,
                seed=seed,
                budget=budget,
                buggy_path=buggy_path,
                fixed_path=fixed_path,
                timeout=timeout,
                population_size=population_size,
            )
            observations.extend(rows)
            run_metadata.append(metadata)
            if report_progress:
                print(
                    "  %d paired inputs, %d target calls, %.3f seconds"
                    % (
                        metadata["evaluation_inputs"],
                        metadata["target_executions"],
                        metadata["total_wall_clock_seconds"],
                    )
                )
    return observations, run_metadata


def _verify_deterministic_results(first, repeated):
    index = lambda rows: {
        (row["method"], int(row["run"]), int(row["test_index"])): row
        for row in rows
    }
    first_index = index(first)
    repeated_index = index(repeated)
    if set(first_index) != set(repeated_index):
        raise RuntimeError("Reproducibility check produced different test counts")
    for key in first_index:
        for field in DETERMINISTIC_FIELDS:
            if first_index[key][field] != repeated_index[key][field]:
                raise RuntimeError(
                    "Reproducibility mismatch for %s at %s: %r != %r"
                    % (
                        field,
                        key,
                        first_index[key][field],
                        repeated_index[key][field],
                    )
                )
    print(
        "Reproducibility check passed: generated inputs, outcomes, and coverage "
        "match for repeated seeds."
    )


def _validate_results(output_dir, budget, runs):
    required_csvs = (
        "random_results.csv",
        "ai_results.csv",
        "all_results.csv",
        "comparison.csv",
        "run_summary.csv",
        "coverage_summary.csv",
        "fault_detection_summary.csv",
        "timing_summary.csv",
    )
    for filename in required_csvs:
        path = output_dir / filename
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError("Expected non-empty result CSV was not written: %s" % path)
        with path.open("r", newline="", encoding="utf-8") as source:
            rows = list(csv.reader(source))
        if len(rows) < 2:
            raise RuntimeError("Result CSV has no data rows: %s" % path)
    for filename in (
        "coverage_comparison.png",
        "fault_detection_comparison.png",
        "generation_overhead_comparison.png",
        "total_runtime_comparison.png",
        "coverage_progression.png",
    ):
        for path in (output_dir / filename, output_dir / "graphs" / filename):
            if not path.is_file() or path.stat().st_size == 0:
                raise RuntimeError("Expected chart was not generated: %s" % path)
    with (output_dir / "all_results.csv").open(
        "r", newline="", encoding="utf-8"
    ) as source:
        rows = list(csv.DictReader(source))
    expected_rows = 2 * runs * budget
    if len(rows) != expected_rows:
        raise RuntimeError(
            "Expected %d evaluated inputs in all_results.csv, found %d"
            % (expected_rows, len(rows))
        )
    for row in rows:
        if int(row["target_execution_count"]) != 2:
            raise RuntimeError("A generated input did not receive exactly two target calls")


def build_parser():
    parser = argparse.ArgumentParser(
        description="Compare seeded random testing with coverage-guided GA testing."
    )
    parser.add_argument(
        "--buggy-source",
        type=Path,
        default=PROJECT_ROOT / "target_program" / "buggy_source",
        help="Path to the expected buggy Git checkout",
    )
    parser.add_argument(
        "--fixed-source",
        type=Path,
        default=PROJECT_ROOT / "target_program" / "fixed_source",
        help="Path to the expected fixed Git checkout",
    )
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--budget", type=int, default=200)
    parser.add_argument("--seed", type=int, default=20261021)
    parser.add_argument("--population-size", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "results",
    )
    parser.add_argument(
        "--pilot",
        action="store_true",
        help="Use the specified pilot design: 2 runs and 50 inputs per method/run",
    )
    parser.add_argument(
        "--verify-reproducibility",
        action="store_true",
        help="Repeat the first-seed runs and compare deterministic outputs",
    )
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.pilot:
        args.runs = 2
        args.budget = 50
    if args.runs < 1 or args.budget < 1:
        raise SystemExit("--runs and --budget must be positive integers")
    if args.population_size < 2:
        raise SystemExit("--population-size must be at least 2")
    if args.timeout <= 0:
        raise SystemExit("--timeout must be greater than zero")

    buggy_path, buggy_commit = _validate_checkout(
        args.buggy_source,
        BUGGY_COMMIT,
        "Buggy",
    )
    fixed_path, fixed_commit = _validate_checkout(
        args.fixed_source,
        FIXED_COMMIT,
        "Fixed",
    )
    print("Verified buggy commit: %s" % buggy_commit)
    print("Verified fixed commit: %s" % fixed_commit)
    _run_original_test(buggy_path, "buggy")
    _run_original_test(fixed_path, "fixed")
    _verify_bug_reproduction(buggy_path, fixed_path, args.timeout)

    observations, run_metadata = _run_experiment(
        runs=args.runs,
        budget=args.budget,
        base_seed=args.seed,
        buggy_path=buggy_path,
        fixed_path=fixed_path,
        timeout=args.timeout,
        population_size=args.population_size,
    )
    if args.verify_reproducibility:
        repeated = _run_experiment(
            runs=1,
            budget=args.budget,
            base_seed=args.seed,
            buggy_path=buggy_path,
            fixed_path=fixed_path,
            timeout=args.timeout,
            population_size=args.population_size,
            report_progress=False,
        )
        _verify_deterministic_results(
            [
                row for row in observations
                if int(row["run"]) == 1
            ],
            repeated[0],
        )

    output_dir = args.output_dir
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    summaries = write_outputs(
        str(output_dir),
        observations,
        run_metadata,
    )[0]

    diagram_path = PROJECT_ROOT / "diagrams" / "system_architecture.png"
    diagram_path.parent.mkdir(parents=True, exist_ok=True)
    generate_architecture_diagram(str(diagram_path))
    _validate_results(output_dir, args.budget, args.runs)

    print("\nExperiment complete.")
    print("Inputs per method/run: %d" % args.budget)
    print("Independent paired seeds: %d, starting at %d" % (args.runs, args.seed))
    print("Each candidate used two target executions (buggy + fixed).")
    print("Results: %s" % output_dir)
    print("Architecture diagram: %s" % diagram_path)
    for summary in summaries:
        print(
            "%s run %s: line coverage %.2f%%, fault-exposing inputs %s/%s, "
            "wall time %.3fs"
            % (
                summary["method"],
                summary["run"],
                float(summary["buggy_line_coverage_pct"] or 0.0),
                summary["fault_exposing_inputs"],
                summary["evaluation_inputs"],
                float(summary["total_wall_clock_seconds"] or 0.0),
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())