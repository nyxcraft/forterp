"""ANSI X3.9-1978 conformance audit -- regression tests for the subtle rules that the
docs/FORTRAN77.md §10 compliance map asserts as "verified" but that previously had no
dedicated unit test (they were covered only incidentally by the FCVS corpus, or not at all).

Each test names the standard section it pins. Run under the F77 dialect on the NATIVE target,
the same configuration as test_f77.py. Values land in COMMON /O/ and are read 1-based.

Provenance: a fresh skeptical re-audit of the compliance map (2026-06). Every expected value
here was first confirmed against the live interpreter, not inferred from the standard."""

import forterp


def _o(body, decl="INTEGER", n=8, block="O"):
    """Run a snippet under F77/NATIVE; return COMMON /O/ as a list (1-based via index-1)."""
    src = f"      PROGRAM T\n      COMMON /O/ N({n})\n      {decl} N\n{body}      END\n"
    return forterp.run_source(src, dialect=forterp.F77, target=forterp.NATIVE).commons[block]


# ---- §6.1 arithmetic: ** is right-associative; unary minus is looser than ** ---------------


def test_power_operator_is_right_associative():
    # 6.1.2.1: a**b**c == a**(b**c).  2**3**2 = 2**9 = 512 (NOT (2**3)**2 = 64).
    assert _o("      N(1)=2**3**2\n      N(2)=2**2**3\n")[:2] == [512, 256]


def test_unary_minus_binds_looser_than_power():
    # 6.1.2.1 / Table interpretation: -A**2 == -(A**2).
    assert _o("      N(1)=-3**2\n")[0] == -9
    assert _o("      REAL N\n      N(1)=-2.0**2\n", decl="REAL")[0] == -4.0


def test_real_base_integer_exponent_leaves_exponent_unconverted():
    # 6.1.4 / Table 3: x**i keeps i an integer -- (-2.0)**3 is the well-defined -8.0,
    # not the domain error a real exponent on a negative base would give.
    assert _o("      REAL N\n      N(1)=(-2.0)**3\n", decl="REAL")[0] == -8.0


# ---- §6.5 operator-class precedence: arithmetic > character > relational > logical ---------


def test_arithmetic_binds_tighter_than_relational():
    # 6.5: 2+3 .GT. 4  parses as (2+3) .GT. 4  -> .TRUE.
    assert _o("      LOGICAL N\n      N(1)=2+3.GT.4\n", decl="LOGICAL")[0]


def test_character_concatenation_binds_tighter_than_relational():
    # 6.5: 'AB'//'C' .EQ. 'ABC'  parses as ('AB'//'C') .EQ. 'ABC' -> .TRUE.
    out = _o(
        "      LOGICAL N\n      CHARACTER*3 C\n      C='AB'//'C'\n      N(1)=C.EQ.'ABC'\n",
        decl="LOGICAL",
    )
    assert out[0]


def test_logical_operator_precedence_not_then_and_then_or():
    # 6.4 / 6.5: .NOT. > .AND. > .OR.
    # .NOT..FALSE..AND..FALSE.  == (.NOT..FALSE.) .AND. .FALSE. == .TRUE..AND..FALSE. == F
    assert not _o("      LOGICAL N\n      N(1)=.NOT..FALSE..AND..FALSE.\n", decl="LOGICAL")[0]
    # .FALSE..OR..TRUE..AND..FALSE. == .FALSE. .OR. (.TRUE..AND..FALSE.) == F
    assert not _o("      LOGICAL N\n      N(1)=.FALSE..OR..TRUE..AND..FALSE.\n", decl="LOGICAL")[0]


# ---- §11.10 DO control variable may be real or double precision ----------------------------


def test_do_control_variable_may_be_real():
    # 11.10: the DO-variable may be integer, real, or double precision.
    # DO X=1.0,2.0,0.5 -> trip count MAX(INT((2-1+0.5)/0.5),0) = 3.
    out = _o(
        "      REAL N\n      K=0\n      DO 1 X=1.0,2.0,0.5\n      K=K+1\n1     CONTINUE\n"
        "      N(1)=K\n",
        decl="REAL",
    )
    assert out[0] == 3.0


def test_do_control_variable_may_be_double_precision():
    out = _o(
        "      DOUBLE PRECISION N\n      K=0\n      DO 1 D=1.0D0,3.0D0\n      K=K+1\n"
        "1     CONTINUE\n      N(1)=K\n",
        decl="DOUBLE PRECISION",
    )
    assert out[0] == 3.0


# ---- §5.2.4 array element ordering is column-major (end-to-end via EQUIVALENCE) ------------


def test_array_storage_is_column_major_via_equivalence():
    # 5.2.4: the first subscript varies fastest. A(2,2) EQUIVALENCEd onto B(4):
    # B(1)=A(1,1), B(2)=A(2,1), B(3)=A(1,2), B(4)=A(2,2).
    out = _o(
        "      DIMENSION A(2,2),B(4)\n      EQUIVALENCE(A,B)\n"
        "      DO 1 I=1,4\n1     B(I)=I\n"
        "      N(1)=A(1,1)\n      N(2)=A(2,1)\n      N(3)=A(1,2)\n      N(4)=A(2,2)\n"
    )
    assert out[:4] == [1, 2, 3, 4]


# ---- §13.5.9.1 Iw.m with m=0 of a zero value -> an all-blank field --------------------------


def test_iw_zero_of_a_zero_value_is_all_blanks():
    # 13.5.9.1: "if m is zero and the value of the internal datum is zero, the field is blank."
    # Use an internal file (no carriage-control) to read the literal field.
    src = (
        "      PROGRAM T\n      COMMON /O/ C\n      CHARACTER*3 C\n"
        "      WRITE(C,'(I3.0)')0\n      END\n"
    )
    assert forterp.run_source(src, dialect=forterp.F77, target=forterp.NATIVE).commons["O"] == [
        "   "
    ]
    # sanity: a nonzero value is unaffected (I3.0 of 5 -> '  5').
    src2 = src.replace(")0\n", ")5\n")
    assert forterp.run_source(src2, dialect=forterp.F77, target=forterp.NATIVE).commons["O"] == [
        "  5"
    ]


# ---- §4.8.1: a character constant must be a nonempty string -------------------------------


def test_empty_character_constant_is_rejected():
    # §4.8.1: "an apostrophe followed by a NONEMPTY string of characters followed by an
    # apostrophe." A zero-length string is meaningless (and a Fortran-90 feature, not F77), so
    # forterp rejects '' on every dialect rather than carry a useless empty token.
    import pytest

    for dialect in (forterp.F77, forterp.FORTRAN10):
        with pytest.raises(forterp.ParseError) as exc:
            forterp.run_source(
                "      PROGRAM T\n      CHARACTER*4 C\n      C=''\n      END\n",
                dialect=dialect,
                target=forterp.NATIVE,
            )
        assert "empty character constant" in str(exc.value)


def test_doubled_apostrophe_is_an_embedded_apostrophe_not_empty():
    # The rejection keys on the RESOLVED value, so a doubled apostrophe (an embedded ') is fine:
    # 'O''CLOCK' is the 7-character string O'CLOCK, not an empty constant.
    eng = forterp.run_source(
        "      PROGRAM T\n      COMMON /O/ C\n      CHARACTER*8 C\n      C='O''CLOCK'\n      END\n",
        dialect=forterp.F77,
        target=forterp.NATIVE,
    )
    assert eng.commons["O"][0] == "O'CLOCK "


# ---- §15.5.2: recursion is rejected by default (was silently wrong; see test_recursion.py) ---


def test_recursion_is_rejected_by_default():
    # §15.5.2: "A subprogram must not reference itself, either directly or indirectly." forterp's
    # static local storage cannot represent recursion, so a re-entry is a hard error rather than
    # the silent wrong answer it used to give. The `recursion` dialect knob permits it correctly
    # -- exercised in tests/test_recursion.py.
    import pytest

    with pytest.raises(forterp.engine.IllegalRecursion):
        _o(
            "      N(1)=IFAC(5)\n      END\n"
            "      INTEGER FUNCTION IFAC(K)\n"
            "      IF(K.LE.1)THEN\n      IFAC=1\n      ELSE\n      IFAC=K*IFAC(K-1)\n      END IF\n"
        )
