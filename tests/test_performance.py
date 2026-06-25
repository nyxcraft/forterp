"""Performance NOTIFIER (not a hard gate) over the bench/ workloads.

Per the chosen policy this never fails the build on a slowdown -- it measures the bench cases,
compares them to the most recent recorded baseline in bench/history.json, and emits a WARNING
when a case got slower (wall time) or changed its executed-statement count. The durable record
is the history table + graph (`python bench/bench.py record` / `graph`).

It is opt-in (the workloads take a few seconds): set FORTERP_BENCH=1 to run it, e.g.

    FORTERP_BENCH=1 pytest tests/test_performance.py -s

The one thing it DOES assert is that each workload still runs at all (a broken interpreter is a
correctness failure, not a performance one) -- the perf deltas are warnings only.
"""

import importlib.util
import os
import pathlib
import warnings

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.skipif(
    not os.environ.get("FORTERP_BENCH"),
    reason="perf workloads are slow; set FORTERP_BENCH=1 to run",
)

WALL_TOLERANCE = 0.25  # warn if a case is >25% slower than the recorded baseline (min-of-N, noisy)


def _bench():
    spec = importlib.util.spec_from_file_location("forterp_bench", ROOT / "bench" / "bench.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_benchmarks_run_and_report_regressions():
    bench = _bench()
    commit = bench._git("rev-parse", "--short", "HEAD") or "working"
    results = bench.measure(ROOT / "src", reps=3)
    history = bench.load_history()

    slow = []
    for case, res in results.items():
        assert "error" not in res, f"benchmark {case!r} failed to run: {res.get('error')}"
        base = bench.baseline_row(history, case, exclude_commit=commit)
        if not base:
            warnings.warn(
                f"perf[{case}]: no baseline recorded yet ({res['steps']} steps, "
                f"{res['ms_min']:.0f} ms) -- run `bench.py record`"
            )
            continue
        if res["steps"] != base["steps"]:
            warnings.warn(
                f"perf[{case}]: executed-statement count changed "
                f"{base['steps']:,} -> {res['steps']:,} (work moved, not just speed)"
            )
        ratio = res["ms_min"] / base["ms_min"]
        msg = (
            f"perf[{case}]: {res['ms_min']:.0f} ms vs baseline {base['ms_min']:.0f} ms "
            f"({(ratio - 1) * 100:+.1f}%, {base['commit']})"
        )
        if ratio > 1 + WALL_TOLERANCE:
            slow.append(msg)
        warnings.warn(msg)

    if slow:  # notify-only: surface prominently, but do NOT fail
        warnings.warn("PERFORMANCE REGRESSION (notify-only): " + "; ".join(slow))
