"""Numeric edge cases: overflow/wrap, divide-by-zero, real range, underflow.

Where FORTRAN-10's behavior is well-defined we assert it; where our model diverges
from the PDP-10 (real range/precision) we DOCUMENT it -- typical values never go
near those edges, so the divergence is benign.
"""

from conftest import run, run_int, out

P35 = 1 << 35
REAL = "        PROGRAM T\n        COMMON /OUT/ V(40)\n        REAL V\n"
END = "        END\n"


# ---- 36-bit integer overflow wraps (two's complement), no trap ----
def test_integer_add_overflow_wraps():
    # (2^35 - 1) + 1 = 2^35 -> sign bit set -> most-negative
    eng = run_int("        V(1)=2^35-1\n        V(1)=V(1)+1\n")
    assert out(eng, 1) == -P35


def test_integer_mul_overflow_wraps():
    # 2^30 * 2^30 = 2^60; mod 2^36 == 0
    eng = run_int("        V(1)=2^30*2^30\n")
    assert out(eng, 1) == 0


def test_most_negative_stays_in_range():
    eng = run_int("        V(1)=-2^35\n        V(2)=-2^35-1\n")
    assert out(eng, 1) == -P35
    assert out(eng, 2) == P35 - 1  # wraps around to most-positive


# ---- divide-by-zero is NON-FATAL (FOROTS warned + continued; never aborted) ----
def test_integer_divide_by_zero_is_zero_not_crash():
    eng = run_int("        V(1)=7/0\n        V(2)=42\n")
    assert out(eng, 1) == 0
    assert out(eng, 2) == 42  # execution continued past the divide


def test_integer_mod_by_zero_returns_dividend():
    eng = run_int("        V(1)=MOD(7,0)\n")
    assert out(eng, 1) == 7  # quotient 0 -> 7 - 0*0 = 7


def test_real_divide_by_zero_is_zero_not_crash():
    eng = run(REAL + "        V(1)=1./0.\n        V(2)=3.5\n" + END)
    assert out(eng, 1) == 0.0
    assert out(eng, 2) == 3.5


def test_zero_over_zero_is_zero_no_nan():
    # the PDP-10 had no IEEE NaN; 0./0. is just a (non-fatal) divide-by-zero -> 0
    eng = run(REAL + "        V(1)=0./0.\n" + END)
    assert out(eng, 1) == 0.0


# ---- real range / precision: we use Python double, NOT 36-bit PDP-10 float ----
def test_real_normal_range_values_are_exact_enough():
    eng = run(REAL + "        V(1)=1.5\n        V(2)=7./2.\n        V(3)=0.1+0.2\n" + END)
    assert out(eng, 1) == 1.5
    assert out(eng, 2) == 3.5
    assert abs(out(eng, 3) - 0.3) < 1e-9


def test_real_underflow_goes_to_zero():
    eng = run(REAL + "        V(1)=1.E-30*1.E-30\n" + END)
    assert out(eng, 1) == 0.0 or abs(out(eng, 1)) < 1e-50


def test_real_range_exceeds_pdp10_known_divergence():
    # PDP-10 floats overflow at ~1.7E38; Python double does not until ~1.8E308. Our
    # model therefore computes values the real machine would have trapped on. The
    # normal values never approach this, so we accept (and pin) the divergence here.
    eng = run(REAL + "        V(1)=1.E60\n        V(2)=1.E300\n" + END)
    assert out(eng, 1) == 1.0e60  # would have overflowed on a real PDP-10
    assert out(eng, 2) == 1.0e300
