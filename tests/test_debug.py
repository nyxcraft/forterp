"""Debugging + profiling via the monitor (forterp.debug.Tracer): PROFILE / COVERAGE /
TRACE / BREAK / STEP, driven through the command monitor.

Programs are strict-F66-clean (the monitor defaults to f66). Lines are numbered from 1,
so a breakpoint at line N targets that source line."""

import os
import tempfile

import pytest

import forterp
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


# ---- OOB-access census (forterp.debug.oob_census) --------------------------
# A(3) with an A(5) overrun: the faithful unchecked behavior (write dropped, read -> 0) is
# unchanged; the census just observes it.
_OOB_SRC = (
    "      PROGRAM T\n      COMMON /OUT/ V(40)\n      DIMENSION A(3)\n"
    "      A(5)=99\n      V(1)=A(5)\n      END\n"
)


def test_oob_census_counts_and_logs_the_overrun():
    with forterp.debug.oob_census() as census:
        forterp.fortran10.run_source(_OOB_SRC)
    assert census.writes >= 1  # A(5)=99 -- OOB write dropped, but censused
    assert census.reads >= 1  # A(5) read -> 0, censused
    assert len(census.sites) >= 2  # both sites logged in "log" mode
    assert {s["op"] for s in census.sites} >= {"read", "write"}
    assert any(s["array"] == "A" for s in census.sites)  # best-effort context captured
    assert forterp.debug.oob_mode() == "off"  # prior mode restored after the block


def test_oob_census_raise_mode_halts_and_restores():
    with pytest.raises(forterp.debug.OobError):
        with forterp.debug.oob_census(mode="raise"):
            forterp.fortran10.run_source(_OOB_SRC)
    assert forterp.debug.oob_mode() == "off"  # restored even when the block raised


def test_set_oob_mode_rejects_unknown_mode():
    with pytest.raises(ValueError):
        forterp.debug.set_oob_mode("bogus")
    assert forterp.debug.oob_mode() == "off"  # left unchanged


def test_oob_counts_are_cumulative_and_log_clears():
    # the standalone (non-context-manager) surface, for callers that snapshot deltas
    forterp.debug.set_oob_mode("log")
    forterp.debug.clear_oob_log()
    r0, w0 = forterp.debug.oob_counts()
    forterp.fortran10.run_source(_OOB_SRC)
    r1, w1 = forterp.debug.oob_counts()
    assert r1 > r0 and w1 > w0  # counters are process-cumulative
    assert forterp.debug.oob_log()  # sites recorded while in "log" mode
    forterp.debug.clear_oob_log()
    assert forterp.debug.oob_log() == []
    forterp.debug.set_oob_mode("off")  # restore the faithful default
