"""Type conversion at assignment boundaries and in mixed expressions."""

from conftest import run, out

REALHEAD = "        PROGRAM T\n        COMMON /OUT/ V(40)\n        REAL V\n"
MIXHEAD = ("        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n"
           "        COMMON /OUT/ V(40)\n        REAL X,Y\n")


def test_real_division_keeps_fraction():
    eng = run(REALHEAD + "        V(1)=7./2.\n        V(2)=7/2\n"
              "        V(3)=7./2\n        END\n")
    # V(2): integer 7/2=3 computed first, then widened to 3.0 on assignment
    assert out(eng, 1) == 3.5
    assert out(eng, 2) == 3.0
    assert out(eng, 3) == 3.5


def test_int_expr_assigned_to_real_is_widened_after_truncation():
    eng = run(MIXHEAD + "        X=7\n        Y=7/2\n"
              "        V(1)=X\n        V(2)=Y\n        END\n")
    assert out(eng, 1) == 7.0
    assert out(eng, 2) == 3.0                     # 7/2 truncates to 3, then -> 3.0


def test_real_assigned_to_integer_truncates_toward_zero():
    eng = run("        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n"
              "        COMMON /OUT/ V(40)\n        REAL X\n"
              "        X=3.9\n        V(1)=X\n        X=-3.9\n        V(2)=X\n        END\n")
    assert out(eng, 1) == 3
    assert out(eng, 2) == -3


def test_INT_and_IFIX_truncate():
    eng = run("        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n"
              "        COMMON /OUT/ V(40)\n"
              "        V(1)=INT(3.9)\n        V(2)=INT(-3.9)\n        V(3)=IFIX(2.5)\n        END\n")
    assert [out(eng, i) for i in range(1, 4)] == [3, -3, 2]


def test_FLOAT_widens():
    eng = run(REALHEAD + "        V(1)=FLOAT(3)\n        V(2)=FLOAT(7)/2.\n        END\n")
    assert out(eng, 1) == 3.0
    assert out(eng, 2) == 3.5


def test_hollerith_assignment_not_numerically_converted():
    # assigning a char literal to an INTEGER stores the packed-ASCII word verbatim;
    # comparing back to the same literal must hold (the signed pack5 fix)
    eng = run("        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n"
              "        COMMON /OUT/ V(40)\n        X='AB'\n        V(1)=0\n"
              "        IF(X=='AB') V(1)=1\n        V(2)=X\n        END\n")
    from f66.parser import pack5
    assert out(eng, 1) == 1
    assert out(eng, 2) == pack5("AB")
