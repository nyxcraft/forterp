"""FORTRAN 66 (X3.9-1966) conformance checks -- the standard's precise clauses turned
into compute-vs-expected tests, in the spirit of the NIST FCVS audit routines. Each
test pins a specific section; a failure here is a real gap vs the standard.
"""

from conftest import run, run_int, out
from forterp.fmt import parse_format, render

REAL = "        PROGRAM T\n        COMMON /OUT/ V(40)\n        REAL V\n"
END = "        END\n"


# ---- §6.1/§6.4 integer arithmetic ------------------------------------------
def test_integer_division_truncates_toward_zero():
    eng = run_int(
        "        V(1)=7/2\n        V(2)=(-7)/2\n        V(3)=7/(-2)\n        V(4)=(-7)/(-2)\n"
    )
    assert [out(eng, i) for i in range(1, 5)] == [3, -3, -3, 3]


def test_integer_term_evaluated_left_to_right():
    # §6.4: integer terms with division are NOT associative -> a*b/c is (a*b)/c
    eng = run_int("        V(1)=2*3/4\n        V(2)=2*(3/4)\n")
    assert out(eng, 1) == 1 and out(eng, 2) == 0


def test_integer_negative_exponent():
    # FORTRAN: int base ** negative int -> 0 for |base|>1, 1 for base 1, +-1 for base -1
    eng = run_int("        V(1)=2^(-1)\n        V(2)=1^(-3)\n        V(3)=(-1)^(-3)\n")
    assert [out(eng, i) for i in range(1, 4)] == [0, 1, -1]


# ---- intrinsic exact semantics (Table 3) -----------------------------------
def test_mod_sign_follows_dividend():
    # MOD(a1,a2) = a1 - [a1/a2]*a2 -> sign of result follows a1
    eng = run_int("        V(1)=MOD(7,3)\n        V(2)=MOD(-7,3)\n        V(3)=MOD(7,-3)\n")
    assert [out(eng, i) for i in range(1, 4)] == [1, -1, 1]


def test_aint_truncates_toward_zero():
    eng = run(REAL + "        V(1)=AINT(3.7)\n        V(2)=AINT(-3.7)\n" + END)
    assert out(eng, 1) == 3.0 and out(eng, 2) == -3.0


def test_idim_positive_difference():
    eng = run_int("        V(1)=IDIM(5,2)\n        V(2)=IDIM(2,5)\n")
    assert out(eng, 1) == 3 and out(eng, 2) == 0


# ---- §7.1.1 assignment conversion (Table 1) --------------------------------
def test_integer_from_real_truncates():
    eng = run_int(
        "        REAL R\n        R=3.99\n        V(1)=R\n        R=-3.99\n        V(2)=R\n"
    )
    assert out(eng, 1) == 3 and out(eng, 2) == -3


def test_real_from_integer_floats():
    eng = run(REAL + "        V(1)=5\n" + END)
    assert out(eng, 1) == 5.0 and isinstance(out(eng, 1), float)


# ---- §7.1.2 control statements ---------------------------------------------
_AIF = (
    "        N=0\n        IF(-5) 10,20,30\n  10    N=1\n        GOTO 99\n"
    "  20    N=2\n        GOTO 99\n  30    N=3\n  99    V(1)=N\n"
)


def test_arithmetic_if_three_way_branch():
    assert out(run_int(_AIF), 1) == 1  # negative
    assert out(run_int(_AIF.replace("IF(-5)", "IF(0)")), 1) == 2  # zero
    assert out(run_int(_AIF.replace("IF(-5)", "IF(7)")), 1) == 3  # positive


def test_computed_goto_out_of_range_falls_through():
    src = (
        "        N=9\n        GOTO (10,20),5\n        N=0\n        GOTO 99\n"
        "  10    N=1\n        GOTO 99\n  20    N=2\n  99    V(1)=N\n"
    )
    assert out(run_int(src), 1) == 0  # index 5 of 2 labels -> fall through


def test_do_one_trip_and_index_left_at_last_value():
    eng = run_int(
        "        K=0\n        DO 5 I=1,0\n  5     K=K+1\n"
        "        V(1)=K\n        V(2)=I\n"
        "        DO 6 J=1,5\n  6     CONTINUE\n        V(3)=J\n"
    )
    assert out(eng, 1) == 1 and out(eng, 2) == 1  # DO I=1,0 runs once, I=1
    assert out(eng, 3) == 5  # index left at last value (DEC)


# ---- §5.1.1.4 signed complex constant parts --------------------------------
def test_complex_constant_signed_parts():
    eng = run(
        REAL + "        COMPLEX C\n        C=(-1.5,+2.5)\n"
        "        V(1)=REAL(C)\n        V(2)=AIMAG(C)\n" + END
    )
    assert out(eng, 1) == -1.5 and out(eng, 2) == 2.5


# ---- §7.2.3.4 FORMAT reversion to the last top-level paren group -----------
def test_format_reversion_reverts_to_last_paren_group():
    # list outlasts the format -> revert to the LAST top-level group, NOT the start
    txt, _ = render(parse_format("(I5,2(I3))"), [1, 2, 3, 4, 5])
    assert txt == "    1  2  3\n  4  5"  # row2 uses I3,I3 (the group), not I5,I3


def test_format_reversion_no_group_restarts_whole():
    # no top-level group -> revert to the start (a bare repeat count is not a group)
    txt, _ = render(parse_format("(2I3)"), [1, 2, 3])
    assert txt == "  1  2\n  3"


# ---- §7.2.3.6 numeric output: overflow -> asterisks, right-justified --------
def test_integer_field_overflow_asterisks():
    txt, _ = render(parse_format("(I2)"), [12345])
    assert txt == "**"


# ---- §7.2.1.3.1 logical .TRUE. in DATA stays "true" (sign-negative) ----------
def test_logical_true_in_data_is_truthy():
    # FCVS FM016/FM023 regression: a LOGICAL array element DATA-initialized .TRUE.
    # must test as true. .TRUE.=-1 (negative sign); a positive 1 would read false.
    eng = run_int(
        "        LOGICAL L\n        DIMENSION L(2)\n"
        "        DATA L/.TRUE.,.FALSE./\n"
        "        IF (L(1)) V(1)=1\n        IF (L(2)) V(2)=1\n"
    )
    assert out(eng, 1) == 1 and out(eng, 2) == 0
