"""Intrinsic functions exercised through the engine."""

from conftest import run, run_int, out


def test_iabs_and_abs():
    eng = run(
        "        PROGRAM T\n        COMMON /OUT/ V(40)\n        REAL V\n"
        "        V(1)=IABS(-7)\n        V(2)=IABS(7)\n"
        "        V(3)=ABS(-3.5)\n        V(4)=ABS(3.5)\n        END\n"
    )
    assert [out(eng, i) for i in range(1, 5)] == [7, 7, 3.5, 3.5]


def test_max0_min0():
    eng = run_int(
        "        V(1)=MAX0(3,7,2)\n        V(2)=MIN0(3,7,2)\n"
        "        V(3)=MAX0(-3,-7)\n        V(4)=MIN0(-3,-7)\n"
    )
    assert [out(eng, i) for i in range(1, 5)] == [7, 2, -3, -7]


def test_amax1_amin1_real():
    eng = run(
        "        PROGRAM T\n        COMMON /OUT/ V(40)\n        REAL V\n"
        "        V(1)=AMAX1(1.5,2.5,0.5)\n        V(2)=AMIN1(1.5,2.5,0.5)\n        END\n"
    )
    assert out(eng, 1) == 2.5
    assert out(eng, 2) == 0.5


def test_mod_intrinsic():
    eng = run_int("        V(1)=MOD(17,5)\n        V(2)=MOD(-17,5)\n        V(3)=MOD(100,7)\n")
    assert [out(eng, i) for i in range(1, 4)] == [2, -2, 2]


def test_lsh_intrinsic():
    eng = run_int("        V(1)=LSH(1,4)\n        V(2)=LSH(256,-4)\n        V(3)=LSH(1,8)\n")
    assert [out(eng, i) for i in range(1, 4)] == [16, 16, 256]


def test_int_float_roundtrip():
    eng = run(
        "        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n"
        "        COMMON /OUT/ V(40)\n        REAL X\n"
        "        X=FLOAT(5)\n        V(1)=INT(X)\n        END\n"
    )
    assert out(eng, 1) == 5
