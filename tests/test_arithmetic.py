"""End-to-end arithmetic/operator semantics through the full pipeline."""

from conftest import run, run_int, out


def test_integer_division_truncates():
    eng = run_int(
        "        V(1)=7/2\n        V(2)=-7/2\n"
        "        V(3)=7/-2\n        V(4)=-7/-2\n        V(5)=1/2\n"
    )
    assert [out(eng, i) for i in range(1, 6)] == [3, -3, -3, 3, 0]


def test_integer_mod_sign_follows_dividend():
    eng = run_int(
        "        V(1)=MOD(17,5)\n        V(2)=MOD(-17,5)\n"
        "        V(3)=MOD(17,-5)\n        V(4)=MOD(-17,-5)\n"
    )
    assert [out(eng, i) for i in range(1, 5)] == [2, -2, 2, -2]


def test_power_operator_integer():
    eng = run_int("        V(1)=2^10\n        V(2)=3^3\n        V(3)=5^0\n        V(4)=10^1\n")
    assert [out(eng, i) for i in range(1, 5)] == [1024, 27, 1, 10]


def test_power_negative_exponent_truncates_to_zero():
    # FORTRAN integer**(negative): 1/(base**n) truncated -> 0 for |base|>1; guarded vs crash
    eng = run_int(
        "        V(1)=2^(-1)\n        V(2)=1^(-3)\n        V(3)=(-1)^(-3)\n        V(4)=(-1)^(-2)\n"
    )
    assert [out(eng, i) for i in range(1, 5)] == [0, 1, -1, 1]


def test_operator_precedence_and_parens():
    eng = run_int(
        "        V(1)=2+3*4\n        V(2)=(2+3)*4\n        V(3)=2^3*2\n        V(4)=10-2-3\n"
    )
    assert [out(eng, i) for i in range(1, 5)] == [14, 20, 16, 5]


def test_unary_minus_and_negative_literals():
    eng = run_int("        V(1)=-5+3\n        V(2)=-(5+3)\n        V(3)=3- -2\n")
    assert [out(eng, i) for i in range(1, 4)] == [-2, -8, 5]


def test_octal_literals():
    eng = run_int('        V(1)="777\n        V(2)="100\n        V(3)="10\n')
    assert [out(eng, i) for i in range(1, 4)] == [511, 64, 8]


def test_symbolic_relationals_yield_truthy_branches():
    # exercise == # < > <= >= via IF; store 1 when the relation holds
    body = (
        "        V(1)=0\n        V(2)=0\n        V(3)=0\n        V(4)=0\n"
        "        V(5)=0\n        V(6)=0\n"
        "        IF(3==3) V(1)=1\n        IF(3#4) V(2)=1\n"
        "        IF(3<4) V(3)=1\n        IF(4>3) V(4)=1\n"
        "        IF(3<=3) V(5)=1\n        IF(3>=4) V(6)=1\n"
    )
    eng = run_int(body)
    assert [out(eng, i) for i in range(1, 7)] == [1, 1, 1, 1, 1, 0]


def test_dotted_logical_operators():
    body = (
        "        LOGICAL A,B\n        A=.TRUE.\n        B=.FALSE.\n"
        "        IF(A.AND..NOT.B) V(1)=1\n"
        "        IF(A.OR.B) V(2)=1\n"
        "        IF(A.AND.B) V(3)=1\n"
        "        IF(B.OR..NOT.A) V(4)=1\n"
    )
    eng = run(
        "        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n"
        "        COMMON /OUT/ V(40)\n        V(1)=0\n        V(2)=0\n"
        "        V(3)=0\n        V(4)=0\n" + body + "        END\n"
    )
    assert [out(eng, i) for i in range(1, 5)] == [1, 1, 0, 0]


def test_integer_overflow_wraps_36bit():
    # 2^35 sets the sign bit -> negative; 2^36 wraps to 0
    eng = run_int("        V(1)=2^35\n        V(2)=2^35-1\n")
    assert out(eng, 1) == -(1 << 35)
    assert out(eng, 2) == (1 << 35) - 1


def test_integer_dot_relational_not_misread_as_real():
    # FORTRAN: 2000/1000.EQ.2 is (2000/1000) .EQ. 2, NOT 2000/1000.<exponent>.
    # (.EQ. starts with 'E', which the number lexer must not grab as an exponent.)
    eng = run_int("        V(1)=0\n        IF(2000/1000.EQ.2) V(1)=1\n")
    assert out(eng, 1) == 1


def test_real_literals_still_lex_after_the_fix():
    eng = run(
        "        PROGRAM T\n        COMMON /OUT/ V(40)\n        REAL V\n"
        "        V(1)=1.5E3\n        V(2)=0\n"
        "        IF(1.5.LT.2.0) V(2)=1\n        END\n"
    )
    assert out(eng, 1) == 1500.0 and out(eng, 2) == 1
