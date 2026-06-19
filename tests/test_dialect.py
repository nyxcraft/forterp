"""Dialect boundary: what the DEC FORTRAN-10 dialect accepts vs what it doesn't.

The interpreter targets DEC FORTRAN-10 (F66-era + DEC extensions),
NOT FORTRAN-77. These tests pin both the supported forms and the F77 constructs that
correctly do NOT parse -- a regression here would mean we drifted toward F77.
"""

from conftest import run, run_int, out
from forterp.dialect import F66

H = "        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n        COMMON /OUT/ V(40)\n"
END = "        END\n"


def _rejected(src, **kw):
    """True if the snippet fails to parse/run (raises from the harness). Extra kwargs
    (e.g. dialect=) pass through to run()."""
    try:
        run(src, **kw)
        return False
    except Exception:
        return True


# ---- supported DEC FORTRAN-10 forms ----
def test_caret_is_the_power_operator():
    assert out(run_int("        V(1)=2^10\n"), 1) == 1024


def test_parenless_parameter_is_accepted():
    # DEC/F66 style: PARAMETER X=val (no parentheses)
    src = (
        "        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n        PARAMETER K=5\n"
        "        COMMON /OUT/ V(40)\n        V(1)=K*2\n" + END
    )
    assert out(run(src), 1) == 10


def test_parenthesized_parameter_also_accepted():
    src = (
        "        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n        PARAMETER (K=5)\n"
        "        COMMON /OUT/ V(40)\n        V(1)=K*2\n" + END
    )
    assert out(run(src), 1) == 10


def test_octal_and_symbolic_relationals_are_dialect_features():
    eng = run_int('        V(1)="20\n        V(2)=0\n        IF(2#3) V(2)=1\n')
    assert out(eng, 1) == 16
    assert out(eng, 2) == 1


# ---- F77-only constructs: correctly NOT supported in this F66 dialect ----
def test_block_if_then_endif_is_rejected():
    assert _rejected(H + "        IF(1==1) THEN\n        V(1)=9\n        ENDIF\n" + END)


def test_do_while_is_rejected():
    assert _rejected(H + "        DO WHILE(V(1)<3)\n        V(1)=V(1)+1\n        END DO\n" + END)


# ---- ** (standard FORTRAN power) is accepted as a synonym for ^ ----
# '^' is the DEC power operator and '**' is standard FORTRAN-66 power; the lexer
# now emits the same power token for both so general F66 code works too.
def test_double_star_is_power_synonym_for_caret():
    assert out(run_int("        V(1)=2**10\n"), 1) == 1024
    assert out(run_int("        V(1)=2**3*2\n"), 1) == 16  # binds tighter than *
    assert out(run_int("        V(1)=2^10\n"), 1) == 1024  # ^ still works


# ---- the dialect AXIS: the same source under FORTRAN10 vs F66 ----
def test_dec_octal_literal_is_gated_by_the_dialect():
    # "nnn is a DEC octal literal under FORTRAN-10 (-> 511); ANSI F66 has no such form,
    # so F66 rejects the SAME source. Exercises the dialect axis through the harness.
    assert out(run_int('        V(1) = "777\n'), 1) == 511  # FORTRAN10 (default)
    assert _rejected(H + '        V(1) = "777\n' + END, dialect=F66)  # ANSI: no octal-"


def test_strict_f66_still_runs_plain_ansi_source():
    # ... while ordinary ANSI F66 runs the same under F66. NB: genuinely plain -- no
    # IMPLICIT (a FORTRAN-10 statement), so V keeps its default REAL type.
    src = "        PROGRAM T\n        COMMON /OUT/ V(40)\n        V(1) = 6 * 7\n        END\n"
    assert out(run(src, dialect=F66), 1) == 42


# ---- F66 rejects the DEC/F77 extensions FORTRAN10 accepts (one per dialect knob) ----
PH = "        PROGRAM T\n        COMMON /OUT/ V(40)\n"  # plain header (no IMPLICIT)


def test_implicit_statement_gated_to_fortran10():
    src = H + "        V(1)=1\n" + END  # H supplies IMPLICIT INTEGER(A-Z)
    assert out(run(src), 1) == 1  # FORTRAN10 (default): accepted
    assert _rejected(src, dialect=F66)  # F66: no IMPLICIT statement


def test_apostrophe_string_gated_to_fortran10():
    src = PH + "        IF ('AB' .EQ. 'AB') V(1) = 1.0\n" + END
    assert out(run(src), 1) == 1.0  # FORTRAN10: accepted
    assert _rejected(src, dialect=F66)  # F66 5.1.1.6: strings are Hollerith nH only


def test_general_subscript_gated_to_fortran10():
    src = (
        PH + "        DIMENSION W(9)\n        I=2\n        J=3\n"
        "        W(I+J)=7.0\n        V(1)=W(5)\n" + END
    )
    assert out(run(src), 1) == 7.0  # FORTRAN10: general subscript accepted
    assert _rejected(src, dialect=F66)  # F66 5.1.3.3: subscript must be c*v±k form


def test_do_bound_expression_gated_to_fortran10():
    src = (
        PH + "        N=3\n        K=0\n        DO 5 I=1,N+1\n    5   K=K+1\n        V(1)=K\n" + END
    )
    assert out(run(src), 1) == 4  # FORTRAN10: DO 1,N+1 -> 4 trips
    assert _rejected(src, dialect=F66)  # F66 7.1.2.8: DO param is constant or variable


def test_complex_numeric_assignment_gated_to_fortran10():
    src = PH + "        COMPLEX Z\n        Z = 1.5\n        V(1) = REAL(Z)\n" + END
    assert out(run(src), 1) == 1.5  # FORTRAN10: real -> complex assignment accepted
    assert _rejected(src, dialect=F66)  # F66 Table 1: COMPLEX <-> numeric prohibited


def test_f66_accepts_the_legal_restricted_forms():
    # the gates must NOT over-reject: a legal c*v+k subscript, a variable DO bound, a
    # complex=complex assignment, and REAL(Z) all run under strict F66.
    src = (
        PH + "        COMPLEX Z\n        DIMENSION W(9)\n        I=1\n        N=3\n"
        "        DO 5 J=1,N\n    5   W(2*I+1)=1.0\n        Z=(1.0,2.0)\n        V(1)=W(3)\n" + END
    )
    assert out(run(src, dialect=F66), 1) == 1.0
