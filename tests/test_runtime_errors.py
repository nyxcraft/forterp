"""Tier-4 runtime/library behavior (V5 Ch15 / Appendix H).

Appendix H: "APR and LIB errors are usually reported as warnings and the program
continues." So a math LIB domain error (SQRT/LOG of a negative arg, ASIN/ACOS of
|arg|>1) must print the manual's message and KEEP RUNNING -- never raise. CALL EXIT
halts (like STOP); ERRSNS(I[,J]) reports the last I/O status; ERRSET caps how many
domain warnings get printed. This is general FORTRAN-10 V5 runtime/library coverage.
"""

import math
from conftest import run, run_int, out
import forterp.ast_nodes as A
from forterp.engine import Engine
from forterp.fmt import unpack_chars

REAL = "        PROGRAM T\n        COMMON /OUT/ V(40)\n        REAL V\n        REAL X\n"
END = "        END\n"
IINT = "        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n        COMMON /OUT/ V(40)\n"


# ---- math LIB domain errors: warn + continue, never raise ------------------
def test_sqrt_negative_warns_and_continues():
    eng = run(REAL + "        V(1)=SQRT(-4.0)\n        V(2)=5.0\n" + END)
    assert out(eng, 1) == 2.0  # recovery: sqrt(|-4|) = 2.0
    assert out(eng, 2) == 5.0  # program CONTINUED past the bad call
    assert "Attempt to take SQRT of Negative Arg." in "".join(eng.out)


def test_asin_acos_out_of_range_clamped_and_warned():
    eng = run(REAL + "        V(1)=ASIN(2.0)\n        V(2)=ACOS(2.0)\n" + END)
    assert abs(out(eng, 1) - math.pi / 2) < 1e-9  # asin clamped to asin(1.0)
    assert out(eng, 2) == 0.0  # acos clamped to acos(1.0)
    text = "".join(eng.out)
    assert "ASIN of Arg. > 1.0 in Magnitude" in text
    assert "ACOS of Arg. > 1.0 in Magnitude" in text


def test_alog_negative_uses_abs():
    eng = run(REAL + "        V(1)=ALOG(-1.0)\n" + END)
    assert out(eng, 1) == 0.0  # recovery: log(|-1|) = log(1.0) = 0.0
    assert "Attempt to take LOG of Negative Arg." in "".join(eng.out)


def test_negative_base_real_exponent_stays_real():
    # F66 6.4: a negative primary raised to a REAL exponent is undefined; faithfully
    # it's a FOROTS domain error -> warn + continue with a REAL result (Python would
    # otherwise silently promote (-4.0)**0.5 to a complex).
    eng = run(REAL + "        V(1)=(-4.0)^0.5\n        V(2)=(-2.0)^3.0\n" + END)
    assert isinstance(out(eng, 1), float) and out(eng, 1) == 2.0  # |-4|**0.5
    assert out(eng, 2) == -8.0  # integer-valued real exponent stays exact/real
    assert "Real Power" in "".join(eng.out)


def test_errset_zero_suppresses_message_but_value_still_recovers():
    eng = run(
        "        PROGRAM T\n        COMMON /OUT/ V(40)\n        REAL V\n"
        "        CALL ERRSET(0)\n        V(1)=SQRT(-9.0)\n" + END
    )
    assert out(eng, 1) == 3.0  # recovery still happens
    assert "Negative" not in "".join(eng.out)  # but nothing is printed


# ---- CALL EXIT terminates the program --------------------------------------
def test_exit_halts_program():
    eng = run_int("        V(1)=1\n        CALL EXIT\n        V(1)=2\n")
    assert out(eng, 1) == 1  # the statement after CALL EXIT did not run


# ---- ERRSNS reports the last I/O status ------------------------------------
def test_errsns_reports_eof_status():
    eng = run(
        "        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n"
        "        COMMON /OUT/ V(40)\n"
        "        OPEN(UNIT=1,FILE='ZZNOEXIST.DAT')\n"
        "        READ(1,END=10) X\n        V(3)=99\n"
        "  10    CALL ERRSNS(I,J)\n        V(1)=I\n        V(2)=J\n" + END
    )
    assert out(eng, 1) == 24  # EOF during READ (Table H-1)
    assert out(eng, 2) == 308  # monitor detail code
    assert out(eng, 3) == 0  # END= branch skipped the post-READ statement


def test_errsns_second_arg_is_optional():
    eng = run(
        "        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n"
        "        COMMON /OUT/ V(40)\n"
        "        OPEN(UNIT=1,FILE='ZZNOEXIST.DAT')\n"
        "        READ(1,END=10) X\n"
        "  10    CALL ERRSNS(I)\n        V(1)=I\n" + END
    )
    assert out(eng, 1) == 24


def test_successful_read_clears_io_error():
    # a successful unformatted read resets the status to (0,0)
    eng = Engine({})
    eng.io[5] = {"recs": [[]], "pos": 0, "mode": "r"}
    eng.last_io_error = (24, 308)
    eng.do_io(A.IoStmt(mode="READ", unit=A.IntLit(5), fmt=None, specs={}, items=[]), None)
    assert eng.last_io_error == (0, 0)


def test_errset_default_is_two():
    # V5 Table 15-3: without CALL ERRSET, messages suppress after N=2 occurrences
    eng = run(
        REAL + "        V(1)=SQRT(-1.0)\n        V(2)=SQRT(-1.0)\n        V(3)=SQRT(-1.0)\n" + END
    )
    assert "".join(eng.out).count("Attempt to take SQRT of Negative Arg.") == 2


# ---- standard library TIME / DATE via the injectable clock (V5 Table 15-3) -
def test_date_uses_fixed_default_clock():
    # the engine's default clock is the fixed DEFAULT_CLOCK (1979-01-01) ->
    # deterministic DATE without any injection
    eng = run(
        IINT + "        DIMENSION R(2)\n        CALL DATE(R)\n"
        "        V(1)=R(1)\n        V(2)=R(2)\n" + END
    )
    text = unpack_chars(out(eng, 1), 5) + unpack_chars(out(eng, 2), 5)
    assert text[:9] == " 1-Jan-79"  # day leading-0 -> blank; month mixed-case


def test_time_and_date_use_injected_clock():
    # a driver/test injects eng.now -> deterministic, V5-formatted time & date
    def setup(eng):
        eng.now = lambda: (1985, 3, 7, 14, 30, 45, 3)

    eng = run(
        IINT + "        DIMENSION R(2)\n        CALL TIME(P)\n        CALL DATE(R)\n"
        "        V(1)=P\n        V(2)=R(1)\n        V(3)=R(2)\n" + END,
        setup=setup,
    )
    assert unpack_chars(out(eng, 1), 5) == "14:30"  # hh:mm
    date = unpack_chars(out(eng, 2), 5) + unpack_chars(out(eng, 3), 5)
    assert date[:9] == " 7-Mar-85"  # day 7 -> ' 7'; month 'Mar'


def test_time_second_arg_is_seconds_and_tenths():
    def setup(eng):
        eng.now = lambda: (1985, 3, 7, 14, 30, 45, 3)

    eng = run(IINT + "        CALL TIME(P,Q)\n        V(1)=P\n        V(2)=Q\n" + END, setup=setup)
    assert unpack_chars(out(eng, 1), 5) == "14:30"
    assert unpack_chars(out(eng, 2), 5) == " 45.3"  # 'bss.t'
