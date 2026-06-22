"""Dialect boundary: what the DEC FORTRAN-10 dialect accepts vs what it doesn't.

The interpreter targets DEC FORTRAN-10 (F66-era + DEC extensions),
NOT FORTRAN-77. These tests pin both the supported forms and the F77 constructs that
correctly do NOT parse -- a regression here would mean we drifted toward F77.
"""

import forterp
from conftest import run, run_int, out
from forterp.dialect import Dialect, F66, FORTRAN10

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


# ---- F66 rejects the DEC/F77 I/O surface (§7.1.3: only READ/WRITE(unit) + aux) ----
def test_extended_io_gated_to_fortran10():
    fmt = "   10   FORMAT(I3)\n"
    for stmt in ("TYPE 10, I", "PRINT 10, I", "ACCEPT 10, I", "READ 10, I"):
        assert _rejected(PH + f"        I=1\n        {stmt}\n" + fmt + END, dialect=F66)
    assert _rejected(PH + "        READ(5,*) I\n" + END, dialect=F66)  # list-directed
    assert _rejected(
        PH + "        DIMENSION B(5)\n        ENCODE(20,10,B) I\n" + fmt + END, dialect=F66
    )
    # the same DEC forms run under FORTRAN10 (default); TYPE / list-directed out need no input
    assert not _rejected(PH + "        I=1\n        TYPE 10, I\n" + fmt + END)
    assert not _rejected(PH + "        I=1\n        WRITE(6,*) I\n" + END)


def test_bare_format_width_gated_to_fortran10():
    src = PH + "        I=1\n        WRITE(6,10) I\n   10   FORMAT(I)\n" + END
    assert _rejected(src, dialect=F66)  # F66 §7.2.3.1: explicit width required
    assert not _rejected(src)  # FORTRAN10: bare I -> V5 default width I15


def test_f66_keeps_unit_formatted_write():
    # the canonical F66 I/O form -- READ/WRITE(unit, label) -- must still parse+run
    src = PH + "        I=1\n        WRITE(6,10) I\n   10   FORMAT(I3)\n" + END
    assert not _rejected(src, dialect=F66)


# ---- DEC/F77 extra intrinsics are gated to FORTRAN10 (F66 = Tables 3 & 4 only) ----
def test_dec_intrinsics_gated_to_fortran10():
    dtan = PH + "        V(1) = DTAN(1.0)\n" + END  # DEC double-precision extra
    assert not _rejected(dtan)  # FORTRAN10 (default): available
    assert _rejected(dtan, dialect=F66)  # strict F66: unknown function
    assert not _rejected(dtan, dialect=Dialect(dec_intrinsics=True))  # F66 opt-in: available
    # the F66 standard library (Tables 3/4) is always available, even strict
    assert not _rejected(PH + "        V(1) = SQRT(4.0)\n" + END, dialect=F66)


def test_random_access_io_gated_to_fortran10():
    # F66 has no random-access I/O; DEFINE FILE, FIND, and the u#r/u'r record forms are DEC.
    df = PH + "        INTEGER NEXT\n        DEFINE FILE 1(100,80,U,NEXT)\n" + END
    rd = PH + "        DIMENSION A(3)\n        READ(1#5) A\n" + END
    assert _rejected(df, dialect=F66)
    assert _rejected(rd, dialect=F66)
    assert _rejected(PH + "        FIND(1'5)\n" + END, dialect=F66)
    # they parse cleanly under FORTRAN10 (parse-only: random I/O needs a connected unit to run)
    forterp.parse_source(df, dialect=FORTRAN10)
    forterp.parse_source(rd, dialect=FORTRAN10)


# ---- DEC operators + syntax extensions, now gated to FORTRAN10 (R2: were ungated leaks) ----
def test_symbolic_relationals_gated_to_fortran10():
    src = PH + "        V(1)=0.0\n        IF(1==1) V(1)=9.0\n" + END
    assert out(run(src), 1) == 9.0  # FORTRAN10: == is a relational
    assert _rejected(src, dialect=F66)  # F66 §6.1: only .EQ./.NE./.LT./.LE./.GT./.GE.


def test_extended_logical_ops_gated_to_fortran10():
    src = PH + "        LOGICAL L\n        L = .TRUE. .XOR. .FALSE.\n        IF(L) V(1)=9.0\n" + END
    assert out(run(src), 1) == 9.0  # FORTRAN10: .XOR.
    assert _rejected(src, dialect=F66)  # F66 §6.1: only .NOT./.AND./.OR.


def test_caret_power_gated_but_double_star_stays_f66():
    assert out(run_int("        V(1)=2^10\n"), 1) == 1024  # FORTRAN10: ^ power
    assert _rejected(PH + "        V(1)=2^10\n" + END, dialect=F66)  # F66: no literal ^
    assert out(run(PH + "        V(1)=2**10\n" + END, dialect=F66), 1) == 1024  # ** stays F66


def test_stmt_separator_gated_to_fortran10():
    src = PH + "        V(1)=1.0 ; V(2)=2.0\n" + END
    eng = run(src)  # FORTRAN10: two statements on one line
    assert out(eng, 1) == 1.0 and out(eng, 2) == 2.0
    assert _rejected(src, dialect=F66)  # F66: one statement per line; ';' is illegal


def test_array_lower_bounds_gated_to_fortran10():
    src = PH + "        DIMENSION A(2:5)\n        A(2)=7.0\n        V(1)=A(2)\n" + END
    assert out(run(src), 1) == 7.0  # FORTRAN10: explicit lower bound
    assert _rejected(src, dialect=F66)  # F66 7.2.1.1.1: arrays are 1..n


def test_parameter_stmt_gated_to_fortran10():
    src = PH + "        PARAMETER (K=5)\n        V(1)=K*2\n" + END
    assert out(run(src), 1) == 10  # FORTRAN10
    assert _rejected(src, dialect=F66)  # PARAMETER added in F77; not in ANSI F66


def test_star_size_gated_to_fortran10():
    src = PH + "        INTEGER*4 K\n        K=5\n        V(1)=K\n" + END
    assert out(run(src), 1) == 5  # FORTRAN10: *n byte-size specifier
    assert _rejected(src, dialect=F66)  # F66: no *n size specifier


def test_alt_return_arg_gated_to_fortran10():
    import pytest

    src = PH + "        CALL SUB(*10)\n   10   V(1)=1.0\n" + END
    forterp.parse_source(src, dialect=FORTRAN10)  # FORTRAN10: parses
    with pytest.raises(forterp.ParseError):
        forterp.parse_source(src, dialect=F66)  # F66: no alternate-return CALL argument


def test_io_list_comma_gated_to_fortran10():
    # DEC FORTRAN-10 accepts an optional comma between the I/O control list and the data
    # list (WRITE(u,f),list); ANSI F66 (7.1.2) does not. Seen in genuine DECUS source.
    src = PH + "        V(1)=7.0\n        WRITE(6,20),V(1)\n   20   FORMAT(F4.1)\n" + END
    eng = run(src, dialect=FORTRAN10)
    assert "7.0" in "".join(eng.printout)  # accepted + runs under FORTRAN10 (unit 6 = LPT)
    assert _rejected(src, dialect=F66)  # rejected under strict F66


def test_end_file_is_the_f66_spelling_of_endfile():
    # 'END FILE u' is the ANSI X3.9-1966 (7.1.3.3) spelling of ENDFILE; one-word ENDFILE is
    # the F77 form. Both parse, in both dialects (blanks are insignificant). DECUS source.
    src = "      PROGRAM T\n      END FILE 2\n      END\n"
    forterp.parse_source(src, dialect=F66)  # the standard F66 form -> no ParseError
    forterp.parse_source(src, dialect=FORTRAN10)  # ... and in the DEC superset


def test_data_is_usable_as_an_array_name():
    # 'DATA' is not a reserved word: DATA(i)=x assigns to an array named DATA (genuine DECUS
    # source), while a real DATA statement still initializes -- both in one unit, ungated.
    src = (
        PH + "        DIMENSION DATA(3)\n        REAL SEED\n        DATA SEED /5.0/\n"
        "        DATA(1)=7.0\n        DATA(2)=8.0\n        V(1)=DATA(1)+DATA(2)+SEED\n" + END
    )
    assert out(run(src), 1) == 20.0
