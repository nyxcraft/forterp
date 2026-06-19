"""Debugging + profiling via the monitor (forterp.debug.Tracer): PROFILE / COVERAGE /
TRACE / BREAK / STEP, driven through the command monitor.

Programs are strict-F66-clean (the monitor defaults to f66). Lines are numbered from 1,
so a breakpoint at line N targets that source line."""

import os
import tempfile

from forterp.monitor import Monitor

# line 4 N=0, 5 DO, 6 N=N+I (runs 3x), 7 CONTINUE
LOOP = (
    "      PROGRAM T\n      COMMON /O/ N\n      INTEGER N\n"
    "      N = 0\n      DO 10 I=1,3\n      N = N + I\n   10 CONTINUE\n      END\n"
)
# line 4 M=42, 5 M=M+1
INCR = (
    "      PROGRAM T\n      COMMON /O/ M\n      INTEGER M\n"
    "      M = 42\n      M = M + 1\n      END\n"
)
# CALL at line 2; K=9 at line 7 inside SUB
CALL = (
    "      PROGRAM T\n      CALL SUB\n      END\n"
    "      SUBROUTINE SUB\n      COMMON /O/ K\n      INTEGER K\n"
    "      K = 9\n      RETURN\n      END\n"
)


def _src(text):
    with tempfile.NamedTemporaryFile("w", suffix=".FOR", delete=False) as f:
        f.write(text)
        return f.name


def drive(lines, **kw):
    it = iter(lines)
    out, err = [], []
    m = Monitor(write=out.append, errwrite=err.append, readline=lambda: next(it, ""), **kw)
    m.run()
    return m, "".join(out), "".join(err)


# ---- profiling / coverage / trace ----
def test_profile_counts_the_hot_line():
    p = _src(LOOP)
    try:
        _, out, _ = drive(["PROFILE ON\n", f"RUN {p}\n", "PROFILE\n", "EXIT\n"])
    finally:
        os.unlink(p)
    assert "T:6" in out and "3" in out  # the loop body ran 3 times


def test_coverage_reports_lines_reached():
    p = _src(LOOP)
    try:
        _, out, _ = drive(["PROFILE ON\n", f"RUN {p}\n", "COVERAGE\n", "EXIT\n"])
    finally:
        os.unlink(p)
    assert "lines" in out and "full" in out  # every executable line ran


def test_trace_echoes_each_statement():
    p = _src(LOOP)
    try:
        _, out, _ = drive(["TRACE ON\n", f"RUN {p}\n", "EXIT\n"])
    finally:
        os.unlink(p)
    assert out.count("T:6") == 3  # body echoed once per trip


# ---- breakpoints / inspection / backtrace / stepping ----
def test_breakpoint_pauses_inspects_and_continues():
    p = _src(INCR)
    try:
        _, out, _ = drive(
            ["BREAK 5\n", f"RUN {p}\n", "M\n", "WHERE\n", "CONT\n", "SHOW /O/\n", "EXIT\n"]
        )
    finally:
        os.unlink(p)
    assert "stopped at T:5" in out  # paused before M = M + 1
    assert "42" in out  # M inspected before the increment
    assert "#0 T:5" in out  # backtrace at the breakpoint
    assert "43" in out  # ran to completion after CONT (SHOW /O/)


def test_backtrace_across_a_call():
    p = _src(CALL)
    try:
        _, out, _ = drive(["BREAK 7\n", f"RUN {p}\n", "WHERE\n", "CONT\n", "EXIT\n"])
    finally:
        os.unlink(p)
    assert "stopped at SUB:7" in out
    assert "#0 SUB:7" in out and "#1 T:2" in out  # SUB called from MAIN's line 2


def test_step_pauses_at_first_then_steps():
    p = _src(INCR)
    try:
        _, out, _ = drive(["STEP\n", f"RUN {p}\n", "step\n", "cont\n", "EXIT\n"])
    finally:
        os.unlink(p)
    assert "stopped at T:4" in out and "stopped at T:5" in out


def test_quit_aborts_the_run():
    p = _src(INCR)
    try:
        _, out, _ = drive(["BREAK 4\n", f"RUN {p}\n", "quit\n", "SHOW /O/\n", "EXIT\n"])
    finally:
        os.unlink(p)
    assert "stopped at T:4" in out
    # quit aborted before M=42 ran, so COMMON M stayed 0 (not 42)
    assert "[0]" in out


# ---- the fast path stays untouched when no debug command is used ----
def test_plain_run_installs_no_tracer():
    p = _src(INCR)
    try:
        m, _, _ = drive([f"RUN {p}\n", "EXIT\n"])
    finally:
        os.unlink(p)
    assert m.last_engine.tracer is None


# ---- R5 fixes: explicit inspect + the off-path instance-__dict__ guard ------
import forterp  # noqa: E402

# a variable named N collides with the `next` command at the (dbg) prompt
_NVAR = (
    "      PROGRAM T\n      COMMON /O/ M\n      INTEGER M, N\n      N = 7\n      M = N\n      END\n"
)


def test_debugger_p_inspects_a_command_named_variable():
    # `N` would run `next`; `p N` / `=N` force inspection of the variable instead (R5).
    p = _src(_NVAR)
    try:
        _, out, _ = drive(["BREAK 5\n", f"RUN {p}\n", "p N\n", "=N\n", "cont\n", "EXIT\n"])
    finally:
        os.unlink(p)
    assert "stopped at T:5" in out
    assert out.count("7\n") >= 2  # inspected once via `p N`, once via `=N`


def test_plain_engine_keeps_tracer_and_frames_as_class_attrs():
    # tracer/frames must stay CLASS defaults; a stray `self.tracer = None` in __init__ would
    # silently reintroduce the ~8% hot-loop regression. Guard a run engine's instance dict.
    eng = forterp.run_source("      PROGRAM T\n      I = 1\n      END\n", dialect=forterp.FORTRAN10)
    assert "tracer" not in eng.__dict__
    assert "frames" not in eng.__dict__
