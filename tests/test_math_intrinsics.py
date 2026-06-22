"""FORTRAN-66 intrinsic function library (math, sign, conversion, max/min)."""

import math

from conftest import out, run, run_int

REAL = "        PROGRAM T\n        COMMON /OUT/ V(40)\n        REAL V\n"
END = "        END\n"


def _real_prog(body):
    return run(REAL + body + END)


def test_sqrt_exp_log():
    eng = _real_prog(
        "        V(1)=SQRT(16.)\n        V(2)=EXP(0.)\n"
        "        V(3)=ALOG(1.)\n        V(4)=ALOG10(1000.)\n"
    )
    assert out(eng, 1) == 4.0
    assert out(eng, 2) == 1.0
    assert out(eng, 3) == 0.0
    assert abs(out(eng, 4) - 3.0) < 1e-9


def test_trig():
    eng = _real_prog("        V(1)=SIN(0.)\n        V(2)=COS(0.)\n        V(3)=ATAN2(1.,1.)\n")
    assert out(eng, 1) == 0.0
    assert out(eng, 2) == 1.0
    assert abs(out(eng, 3) - math.pi / 4) < 1e-9


def test_sign_transfer():
    # SIGN(a,b) = |a| with the sign of b; ISIGN is the integer form
    eng = _real_prog("        V(1)=SIGN(2.,-1.)\n        V(2)=SIGN(2.,5.)\n")
    assert out(eng, 1) == -2.0
    assert out(eng, 2) == 2.0
    eng2 = run_int("        V(1)=ISIGN(7,-3)\n        V(2)=ISIGN(-7,3)\n")
    assert out(eng2, 1) == -7
    assert out(eng2, 2) == 7


def test_positive_difference_dim():
    eng = run_int("        V(1)=IDIM(7,3)\n        V(2)=IDIM(3,7)\n")
    assert out(eng, 1) == 4
    assert out(eng, 2) == 0


def test_aint_anint_nint():
    eng = _real_prog(
        "        V(1)=AINT(3.7)\n        V(2)=AINT(-3.7)\n"
        "        V(3)=ANINT(2.5)\n        V(4)=ANINT(-2.5)\n"
    )
    assert out(eng, 1) == 3.0  # truncate toward zero
    assert out(eng, 2) == -3.0
    assert out(eng, 3) == 3.0  # round half away from zero
    assert out(eng, 4) == -3.0
    assert out(run_int("        V(1)=NINT(2.6)\n        V(2)=NINT(-2.6)\n"), 1) == 3


def test_amod_real_remainder():
    eng = _real_prog("        V(1)=AMOD(7.5,2.0)\n")
    assert out(eng, 1) == 1.5


def test_typed_max_min_variants():
    # MAX1: real args -> integer max; AMAX0: integer args -> real max
    eng = run_int("        V(1)=MAX1(1.9,2.1,0.5)\n        V(2)=MIN1(1.9,2.1,0.5)\n")
    assert out(eng, 1) == 2
    assert out(eng, 2) == 0
    eng2 = _real_prog("        V(1)=AMAX0(3,7,2)\n")
    assert out(eng2, 1) == 7.0


def test_asin_acos_and_degree_trig():
    eng = _real_prog(
        "        V(1)=ASIN(1.)\n        V(2)=ACOS(1.)\n"
        "        V(3)=SIND(90.)\n        V(4)=COSD(0.)\n"
    )
    assert abs(out(eng, 1) - math.pi / 2) < 1e-9
    assert out(eng, 2) == 0.0
    assert abs(out(eng, 3) - 1.0) < 1e-9
    assert abs(out(eng, 4) - 1.0) < 1e-9


def test_double_variants():
    eng = _real_prog(
        "        V(1)=DFLOAT(7)\n        V(2)=DMAX1(1.5,2.5)\n        V(3)=DMIN1(1.5,2.5)\n"
    )
    assert [out(eng, i) for i in range(1, 4)] == [7.0, 2.5, 1.5]


def test_conversions_idint_dble():
    eng = run_int("        V(1)=IDINT(3.9)\n")
    assert out(eng, 1) == 3
    eng2 = _real_prog("        V(1)=DBLE(5)\n        V(2)=SNGL(2.5)\n")
    assert out(eng2, 1) == 5.0
    assert out(eng2, 2) == 2.5


def test_intrinsic_does_not_shadow_array_access():
    # an array named like an intrinsic (MIN) is still indexed, not called
    src = (
        "        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n"
        "        DIMENSION MIN(3)\n        COMMON /OUT/ V(40)\n"
        "        DATA MIN/11,22,33/\n        V(1)=MIN(2)\n" + END
    )
    assert out(run(src), 1) == 22
