#!/usr/bin/env python3
"""forterp performance benchmark + history.

Times two fixed workloads through the interpreter and tracks the numbers over git history,
so a slowdown is visible (a *notification*, not a hard gate -- see tests/test_performance.py):

  loop  -- a tight DO loop (1M iterations): raw interpreter per-statement overhead.
  fft   -- 100x forward+inverse 256-point FFT (demos' Singleton FFT): a real numeric workload.

Two metrics per case: `steps` (executed statements -- deterministic, identical every run, so a
change means the *amount of work* moved) and `ms_min` (min-of-N wall time -- the actual speed,
environment-sensitive so always min-of-N and compared with a wide tolerance).

Methodology (learned the hard way): compare MINIMUMS, run each timing in a fresh subprocess, and
time an older commit by pointing PYTHONPATH at a `git worktree` of it -- never `git checkout` the
working tree between timed runs (.pyc / file-cache churn confounds it).

Commands:
  python bench/bench.py run                 # time the current tree, print a table vs the baseline
  python bench/bench.py record              # ... and append the current commit to history.json
  python bench/bench.py backfill <commit…>  # time past commits (worktree + PYTHONPATH) into history
  python bench/bench.py graph               # ASCII sparklines + write bench/history.svg
"""

import datetime
import json
import os
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
BENCH = ROOT / "bench"
CASES_DIR = BENCH / "cases"
HISTORY = BENCH / "history.json"
RUNNER = BENCH / "_runner.py"

# Fixed workloads (the bench owns frozen copies, so demos/ edits never move the numbers).
DIALECT, TARGET, REPS = "fortran10", "native", 5
CASES = {
    "loop": {"files": ["cases/LOOP.FOR"], "program": "LOOP"},
    "fft": {"files": ["cases/FFTBM.FOR", "cases/FFT.FOR"], "program": "FFTBM"},
}


def _case_payload(name, reps=REPS):
    c = CASES[name]
    return {
        "files": [str(CASES_DIR / pathlib.Path(f).name) for f in c["files"]],
        "program": c["program"],
        "dialect": DIALECT,
        "target": TARGET,
        "reps": reps,
    }


def measure(src_path, reps=REPS):
    """Time every case against the interpreter at `src_path` (a src/ dir). Returns {case: res}."""
    env = {**os.environ, "PYTHONPATH": str(src_path)}
    out = {}
    for name in CASES:
        payload = _case_payload(name, reps)
        payload["src"] = str(src_path)  # the runner verifies forterp imported from here
        payload = json.dumps(payload)
        r = subprocess.run(
            [sys.executable, str(RUNNER), payload], capture_output=True, text=True, env=env
        )
        try:
            out[name] = json.loads(r.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            out[name] = {"error": (r.stderr or r.stdout or "no output").strip()[:120]}
    return out


def _git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def load_history():
    if HISTORY.exists():
        return json.loads(HISTORY.read_text())
    return {"schema": 1, "records": []}


def save_history(h):
    HISTORY.write_text(json.dumps(h, indent=2) + "\n")


def _append(h, commit, date, results):
    py = f"{sys.version_info.major}.{sys.version_info.minor}"
    h["records"] = [r for r in h["records"] if not (r["commit"] == commit and r["py"] == py)]
    for case, res in results.items():
        if "error" in res:
            continue
        h["records"].append(
            {
                "commit": commit,
                "date": date,
                "py": py,
                "case": case,
                "steps": res["steps"],
                "ms_min": res["ms_min"],
            }
        )


def baseline_row(h, case, exclude_commit=None):
    """The comparison point: the git-history-latest recorded `case` row that is NOT the current
    commit -- i.e. the most recent prior measurement, regardless of insertion order."""
    ordered = _ordered(h).get(case, [])
    prior = [r for r in ordered if r["commit"] != exclude_commit]
    return prior[-1] if prior else None


def cmd_run(record=False):
    h = load_history()
    commit = _git("rev-parse", "--short", "HEAD") or "working"
    print(f"forterp bench @ {commit}  (dialect={DIALECT}, target={TARGET}, min of {REPS})\n")
    results = measure(ROOT / "src")
    print(f"  {'case':6} {'steps':>12} {'ms_min':>10}   vs last recorded")
    for name, res in results.items():
        if "error" in res:
            print(f"  {name:6} ERROR: {res['error']}")
            continue
        base = baseline_row(h, name, exclude_commit=commit)
        note = ""
        if base:
            dms = 100.0 * (res["ms_min"] - base["ms_min"]) / base["ms_min"]
            dst = res["steps"] - base["steps"]
            note = f"{dms:+.1f}% time" + (f", {dst:+d} steps" if dst else "")
        print(f"  {name:6} {res['steps']:>12,} {res['ms_min']:>10.1f}   {note}")
    if record:
        _append(h, commit, datetime.date.today().isoformat(), results)
        save_history(h)
        print(f"\nrecorded {commit} to {HISTORY.relative_to(ROOT)}")


def cmd_backfill(commits):
    h = load_history()
    for ref in commits:
        commit = _git("rev-parse", "--short", ref)
        date = _git("show", "-s", "--format=%cs", ref)  # author/commit short date
        with tempfile.TemporaryDirectory() as wt:
            add = subprocess.run(
                ["git", "worktree", "add", "--detach", wt, ref],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            if add.returncode != 0:
                print(f"  {commit}: worktree failed: {add.stderr.strip()[:80]}")
                continue
            try:
                results = measure(pathlib.Path(wt) / "src", reps=3)
            finally:
                subprocess.run(
                    ["git", "worktree", "remove", "--force", wt], cwd=ROOT, capture_output=True
                )
        ok = {k: v for k, v in results.items() if "error" not in v}
        _append(h, commit, date, results)
        save_history(h)  # save after each commit, so an interrupted long backfill keeps progress
        summary = ", ".join(f"{k}={v['ms_min']:.0f}ms" for k, v in ok.items()) or "no cases ran"
        gaps = [k for k, v in results.items() if "error" in v]
        print(f"  {commit} ({date}): {summary}" + (f"  [gaps: {gaps}]" if gaps else ""))
    print(f"\nhistory now has {len(h['records'])} rows; run `bench.py graph`")


_BLOCKS = "▁▂▃▄▅▆▇█"


def _spark(values):
    lo, hi = min(values), max(values)
    if hi == lo:
        return _BLOCKS[0] * len(values)
    return "".join(_BLOCKS[int((v - lo) / (hi - lo) * (len(_BLOCKS) - 1))] for v in values)


def _ordered(h):
    """Records grouped by case, in git-history order (oldest→newest), de-duped by commit."""
    order = _git("rev-list", "--topo-order", "--reverse", "HEAD").split()  # full hashes, old→new

    def rank(commit):  # records store short hashes; match by prefix against the full list
        for i, full in enumerate(order):
            if full.startswith(commit):
                return i
        return len(order)  # not an ancestor of HEAD (e.g. a sibling branch) -> sort last

    out = {}
    for case in CASES:
        rows = [r for r in h["records"] if r["case"] == case]
        rows.sort(key=lambda r: rank(r["commit"]))
        out[case] = rows
    return out


def cmd_graph():
    h = load_history()
    by = _ordered(h)
    print("forterp performance over time (oldest → newest)\n")
    for case, rows in by.items():
        if not rows:
            continue
        times = [r["ms_min"] for r in rows]
        print(f"  {case:5} ms_min  {_spark(times)}   {times[0]:.0f} → {times[-1]:.0f} ms")
        print(f"  {'':5} commits {' '.join(r['commit'][:7] for r in rows)}")
        print()
    _write_svg(by)
    print(f"wrote {(BENCH / 'history.svg').relative_to(ROOT)}")


def _write_svg(by):
    W, H, pad = 720, 240, 40
    colors = {"loop": "#2b8cbe", "fft": "#e6550d"}
    plot_h = H - 2 * pad
    rows_all = [r for rows in by.values() for r in rows]
    hi = max((r["ms_min"] for r in rows_all), default=1.0)

    def y_of(ms):
        return (H - pad) - plot_h * (ms / hi)

    p = [
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{W}" height="{H}" font-family="sans-serif">',
        f'<rect width="{W}" height="{H}" fill="white"/>',
        f'<text x="{pad}" y="24" font-size="14" font-weight="bold">'
        "forterp ms_min over git history (lower is better)</text>",
    ]
    for case, rows in by.items():
        if not rows:
            continue
        col = colors.get(case, "#666")
        n = max(len(rows) - 1, 1)
        pts = []
        for i, r in enumerate(rows):
            x = pad + (W - 2 * pad) * (i / n)
            y = y_of(r["ms_min"])
            pts.append(f"{x:.1f},{y:.1f}")
            p.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{col}"/>')
        p.append(
            f'<polyline fill="none" stroke="{col}" stroke-width="2" points="{" ".join(pts)}"/>'
        )
        p.append(
            f'<text x="{pad + 4:.0f}" y="{y_of(rows[0]["ms_min"]) - 6:.1f}" '
            f'font-size="11" fill="{col}">{case}</text>'
        )
    p.append("</svg>")
    (BENCH / "history.svg").write_text("\n".join(p) + "\n")


def main(argv):
    cmd = argv[0] if argv else "run"
    if cmd == "run":
        cmd_run(record=False)
    elif cmd == "record":
        cmd_run(record=True)
    elif cmd == "backfill":
        if len(argv) < 2:
            sys.exit("usage: bench.py backfill <commit> [commit…]")
        cmd_backfill(argv[1:])
    elif cmd == "graph":
        cmd_graph()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
