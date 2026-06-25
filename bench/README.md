# forterp performance benchmark

Tracks interpreter speed over git history so a slowdown is **noticed** (a notification, not a
hard gate — the gate policy is notify-only). Two fixed workloads, run through the engine:

| Case | Workload | Probes |
|------|----------|--------|
| `loop` | a 1,000,000-iteration `DO` loop (`X = X + 1.0D0`) | raw interpreter per-statement overhead |
| `fft`  | 100× forward+inverse 256-point FFT (the Singleton FFT from `demos/`) | a realistic numeric workload |

Each case reports two numbers:

- **`steps`** — executed statements. *Deterministic* (identical every run), so a change means the
  *amount of work* moved (an algorithmic change), not just speed.
- **`ms_min`** — minimum wall time over N runs. The actual speed; environment-sensitive, hence
  always min-of-N and compared with a wide tolerance.

The workloads are **frozen copies** under `cases/` (so editing `demos/` never moves the numbers),
run under `dialect=fortran10, target=native`.

## Usage

```sh
python bench/bench.py run                 # time the current tree, print a table vs the baseline
python bench/bench.py record              # ...and append the current commit to history.json
python bench/bench.py backfill <commit…>  # time past commits (git worktree + PYTHONPATH) into history
python bench/bench.py graph               # ASCII sparklines + (re)write bench/history.svg
```

`bench/history.json` is the committed data table (one row per `{commit, case}`); `bench/history.svg`
is the rendered line chart (dependency-free; no matplotlib).

The pytest [`tests/test_performance.py`](../tests/test_performance.py) is the **notifier**: opt-in
via `FORTERP_BENCH=1 pytest tests/test_performance.py -s`, it warns on a slowdown but never fails
the build (it only asserts the workloads still *run*).

## Methodology (learned the hard way)

- **Compare minimums**, not means — the min is the least-contended run.
- **Run each timing in a fresh subprocess** (`_runner.py`), and time an older commit by pointing
  `PYTHONPATH` at a `git worktree` of it — **never `git checkout` the working tree between timed
  runs** (`.pyc` / file-cache churn confounds the comparison).
- **Measure run-only** (parse once, outside the timed loop). A commit predating
  `Engine.run_program` is reported as a *gap*, not measured a different (parse-inflated) way — a
  misleading data point is worse than none.
