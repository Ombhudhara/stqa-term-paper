"""Evaluate each generated candidate once on each benchmark implementation."""

import json
import re
import time

from .random_testing import canonical_json


FAULT_ID = "BugsInPy-youtube-dl-1"


def _normalized_exception_message(message):
    return re.sub(r"0x[0-9a-fA-F]+", "0x<address>", message or "")


def semantic_outcome(observation):
    """Return stable, observable behavior without incidental timing details."""
    if observation.get("ok"):
        result = observation.get("result", {})
        return (
            "return",
            result.get("type"),
            canonical_json(result.get("value")),
        )
    return (
        "exception",
        observation.get("exception"),
        _normalized_exception_message(observation.get("message")),
    )


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


class TestRunner(object):
    def __init__(self, buggy_worker, fixed_worker):
        self.buggy_worker = buggy_worker
        self.fixed_worker = fixed_worker

    def evaluate(
        self,
        test_input,
        method,
        run_number,
        seed,
        test_number,
        generation_seconds,
    ):
        started = time.perf_counter()
        buggy = self.buggy_worker.execute(test_input)
        fixed = self.fixed_worker.execute(test_input)
        pair_seconds = time.perf_counter() - started
        distinguishes = (
            buggy.get("ok") is True
            and fixed.get("ok") is True
            and semantic_outcome(buggy) != semantic_outcome(fixed)
        )
        dct = test_input["dct"]

        return {
            "method": method,
            "run": run_number,
            "test_index": test_number,
            "seed": seed,
            "input_id": test_input.get("input_id", ""),
            "filter_part": test_input["filter_part"],
            "dct_json": _json(dct),
            "buggy_ok": buggy.get("ok"),
            "buggy_result_type": buggy.get("result", {}).get("type", ""),
            "buggy_result_json": _json(buggy.get("result", {}).get("value"))
            if buggy.get("ok") else "",
            "buggy_result_repr": buggy.get("result", {}).get("repr", ""),
            "buggy_exception": buggy.get("exception", ""),
            "buggy_message": buggy.get("message", ""),
            "fixed_ok": fixed.get("ok"),
            "fixed_result_type": fixed.get("result", {}).get("type", ""),
            "fixed_result_json": _json(fixed.get("result", {}).get("value"))
            if fixed.get("ok") else "",
            "fixed_result_repr": fixed.get("result", {}).get("repr", ""),
            "fixed_exception": fixed.get("exception", ""),
            "fixed_message": fixed.get("message", ""),
            "distinguishes_versions": distinguishes,
            "fault_id": FAULT_ID if distinguishes else "",
            "buggy_coverage_lines": _json(buggy.get("coverage_lines", [])),
            "buggy_coverage_arcs": _json(buggy.get("coverage_arcs", [])),
            "buggy_coverage_branch_arcs": _json(
                buggy.get("coverage_branch_arcs", [])
            ),
            "buggy_total_statements": buggy.get("total_statements", 0),
            "buggy_total_branches": buggy.get("total_branches"),
            "buggy_branch_coverage_supported": buggy.get(
                "branch_coverage_supported", False
            ),
            "fixed_coverage_lines": _json(fixed.get("coverage_lines", [])),
            "fixed_coverage_arcs": _json(fixed.get("coverage_arcs", [])),
            "fixed_coverage_branch_arcs": _json(
                fixed.get("coverage_branch_arcs", [])
            ),
            "fixed_total_statements": fixed.get("total_statements", 0),
            "fixed_total_branches": fixed.get("total_branches"),
            "fixed_branch_coverage_supported": fixed.get(
                "branch_coverage_supported", False
            ),
            "generation_time_seconds": generation_seconds,
            "buggy_execution_seconds": buggy.get("execution_seconds", 0.0),
            "fixed_execution_seconds": fixed.get("execution_seconds", 0.0),
            "target_execution_seconds": (
                buggy.get("execution_seconds", 0.0)
                + fixed.get("execution_seconds", 0.0)
            ),
            "pair_roundtrip_seconds": pair_seconds,
            "target_execution_count": 2,
        }, buggy