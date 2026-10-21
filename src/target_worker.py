"""Isolated JSON-line worker for the BugsInPy youtube-dl target."""

import json
import os
import queue
import inspect
import importlib
import subprocess
import sys
import threading
import time
import traceback


class TargetWorkerError(RuntimeError):
    """Raised when the target worker cannot safely execute a request."""


class TargetWorkerTimeout(TargetWorkerError):
    """Raised when a target request exceeds its configured timeout."""


def _json_safe(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return repr(value)


def _worker_main(target_root):
    target_root = os.path.realpath(target_root)
    if "youtube_dl" in sys.modules:
        raise RuntimeError("youtube_dl was imported before target isolation")
    sys.path.insert(0, target_root)

    try:
        utils = importlib.import_module("youtube_dl.utils")

        utils_file = os.path.realpath(utils.__file__)
        if os.path.commonpath([target_root, utils_file]) != target_root:
            raise RuntimeError(
                "Imported youtube_dl.utils outside requested target root: %s"
                % utils_file
            )
        target_function = utils._match_one
        function_source, function_start = inspect.getsourcelines(target_function)
        function_end = function_start + len(function_source) - 1
        from coverage import Coverage
        coverage = Coverage(
            data_file=None,
            branch=True,
            include=[utils_file],
            config_file=False,
        )
        static_analysis = coverage._analyze(utils_file)
        function_statements = set(
            line for line in static_analysis.statements
            if function_start <= line <= function_end
        )
        branch_stats = None
    except Exception as exc:
        print(json.dumps({
            "ready": False,
            "error": repr(exc),
            "traceback": traceback.format_exc(),
        }), flush=True)
        return 2

    print(json.dumps({
        "ready": True,
        "utils_file": utils_file,
        "target_root": target_root,
    }), flush=True)

    coverage.start()
    request_number = 0
    for line in sys.stdin:
        try:
            request_number += 1
            request = json.loads(line)
            filter_part = request["filter_part"]
            data_dict = request["dct"]
            if not isinstance(filter_part, str) or not isinstance(data_dict, dict):
                raise ValueError("Expected a string filter_part and dictionary dct")

            context = "input-%d" % request_number
            coverage.switch_context(context)
            started = time.perf_counter()
            try:
                result = target_function(filter_part, data_dict)
                outcome = {
                    "ok": True,
                    "result": {
                        "type": type(result).__name__,
                        "value": _json_safe(result),
                        "repr": repr(result),
                    },
                }
            except Exception as exc:
                outcome = {
                    "ok": False,
                    "exception": type(exc).__name__,
                    "message": str(exc),
                }
            finally:
                outcome["execution_seconds"] = time.perf_counter() - started

            data = coverage.get_data()
            coverage.switch_context("")
            data.set_query_context(context)
            executed_lines = data.lines(utils_file) or []
            executed_arcs = data.arcs(utils_file) or []
            data.set_query_context(None)

            if branch_stats is None:
                analysis = coverage._analyze(utils_file)
                try:
                    all_branch_stats = analysis.branch_stats()
                    branch_stats = {
                        line: counts for line, counts in all_branch_stats.items()
                        if function_start <= line <= function_end
                    }
                except (AttributeError, NotImplementedError):
                    branch_stats = None
            if branch_stats is None:
                branch_lines = []
                branch_arcs = []
                total_branches = None
                branch_supported = False
            else:
                branch_lines = sorted(branch_stats)
                branch_arcs = sorted(
                    (int(source), int(destination))
                    for source, destination in executed_arcs
                    if source in branch_stats
                )
                total_branches = sum(
                    counts[0] for counts in branch_stats.values()
                )
                branch_supported = True

            outcome.update({
                "coverage_lines": sorted(
                    set(
                        line for line in executed_lines
                        if line in function_statements
                    )
                ),
                "coverage_arcs": sorted(
                    (int(source), int(destination))
                    for source, destination in set(executed_arcs)
                    if function_start <= source <= function_end
                ),
                "branch_lines": branch_lines,
                "coverage_branch_arcs": branch_arcs,
                "total_statements": len(function_statements),
                "total_branches": total_branches,
                "branch_coverage_supported": branch_supported,
                "function_start": function_start,
                "function_end": function_end,
            })
            print(json.dumps(outcome, sort_keys=True), flush=True)
        except Exception as exc:
            print(json.dumps({
                "worker_error": repr(exc),
                "traceback": traceback.format_exc(),
            }), flush=True)

    coverage.stop()
    return 0


class TargetWorker(object):
    """Keep one fresh, target-specific interpreter process for repeated calls."""

    def __init__(self, target_root, timeout=10.0, python_executable=None):
        self.target_root = os.path.realpath(os.path.abspath(target_root))
        self.timeout = float(timeout)
        self.startup_timeout = max(self.timeout, 60.0)
        self.python_executable = python_executable or sys.executable
        if not os.path.isdir(self.target_root):
            raise TargetWorkerError(
                "Target source directory does not exist: %s" % self.target_root
            )

        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env.pop("PYTHONHOME", None)
        script_path = os.path.abspath(__file__)
        self._process = subprocess.Popen(
            [
                self.python_executable,
                "-I",
                script_path,
                "--worker",
                self.target_root,
            ],
            cwd=self.target_root,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1,
        )
        self._messages = queue.Queue()
        self._stderr_chunks = []
        self._stdout_thread = threading.Thread(
            target=self._read_stdout, daemon=True
        )
        self._stderr_thread = threading.Thread(
            target=self._read_stderr, daemon=True
        )
        self._stdout_thread.start()
        self._stderr_thread.start()

        try:
            ready = self._read_message(self.startup_timeout)
        except Exception:
            self.close()
            raise
        if not ready.get("ready"):
            self.close()
            raise TargetWorkerError(
                "Target import failed for %s: %s\n%s"
                % (
                    self.target_root,
                    ready.get("error", "unknown import error"),
                    ready.get("traceback", ""),
                )
            )

        expected_root = os.path.normcase(self.target_root)
        actual_file = os.path.realpath(ready.get("utils_file", ""))
        if os.path.commonpath([expected_root, os.path.normcase(actual_file)]) != expected_root:
            self.close()
            raise TargetWorkerError(
                "Worker loaded utils.py from unexpected location: %s" % actual_file
            )
        self.utils_file = actual_file

    def _read_stdout(self):
        try:
            for line in self._process.stdout:
                self._messages.put(line)
        finally:
            self._messages.put(None)

    def _read_stderr(self):
        for line in self._process.stderr:
            self._stderr_chunks.append(line)
            if len(self._stderr_chunks) > 200:
                del self._stderr_chunks[:100]

    def _read_message(self, timeout):
        try:
            line = self._messages.get(timeout=timeout)
        except queue.Empty:
            self._process.kill()
            raise TargetWorkerTimeout(
                "Timed out waiting for target worker response (%s seconds)"
                % timeout
            )
        if line is None:
            stderr = "".join(self._stderr_chunks).strip()
            raise TargetWorkerError(
                "Target worker exited unexpectedly (exit code %s)%s"
                % (
                    self._process.poll(),
                    ("\n" + stderr) if stderr else "",
                )
            )
        try:
            message = json.loads(line)
        except ValueError as exc:
            raise TargetWorkerError(
                "Target worker returned invalid JSON: %r (%s)" % (line, exc)
            )
        if "worker_error" in message:
            raise TargetWorkerError(
                "Target worker request failed: %s\n%s"
                % (
                    message["worker_error"],
                    message.get("traceback", ""),
                )
            )
        return message

    def execute(self, test_input):
        if self._process.poll() is not None:
            raise TargetWorkerError("Target worker process is no longer running")
        request = {
            "filter_part": test_input["filter_part"],
            "dct": test_input["dct"],
        }
        try:
            self._process.stdin.write(json.dumps(request, sort_keys=True) + "\n")
            self._process.stdin.flush()
        except (IOError, OSError) as exc:
            raise TargetWorkerError("Unable to send request to target worker: %s" % exc)
        return self._read_message(self.timeout)

    def close(self):
        process = getattr(self, "_process", None)
        if process is None or process.poll() is not None:
            return
        try:
            if process.stdin:
                process.stdin.close()
            process.wait(timeout=2.0)
        except (IOError, OSError, subprocess.TimeoutExpired):
            process.kill()
            process.wait()

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc_value, _traceback):
        self.close()


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "--worker":
        sys.stderr.write(
            "Usage: target_worker.py --worker <target-source-directory>\n"
        )
        raise SystemExit(2)
    raise SystemExit(_worker_main(sys.argv[2]))
