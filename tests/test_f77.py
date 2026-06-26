"""FORTRAN 77 dialect.

Phase 1 -- structured control: block IF / ELSE IF / ELSE / END IF and DO WHILE / END DO
(the parser emits markers; parser._lower_structured rewrites them to the engine's flat
label+GOTO form), SAVE, INTRINSIC, and generic intrinsics.

Phase 2 -- CHARACTER: declarations with a length, blank-pad/truncate assignment, concatenation
(//), blank-padded comparison, LEN/CHAR/ICHAR/INDEX/LGE..LLT, and substrings S(i:j) (read +
assignable lvalue, incl. array-element substrings). Under the F77 dialect a string literal is a
CHARACTER constant (a Python str), not a Hollerith packed word.

Phase 3 -- I/O: A-format CHARACTER WRITE/READ (the A field is a str; input fits to the declared
length by the F77 rightmost/blank-fill rule), internal files (READ/WRITE to a CHARACTER variable),
and INQUIRE (by FILE / by UNIT: EXIST/OPENED/NUMBER/NAMED/NAME/IOSTAT).

Runs under the F77 dialect (NATIVE target) unless a test says otherwise."""

import io

import pytest

import forterp


def _out(src, dialect=forterp.F77, block="O"):
    """Run a snippet under the given dialect and return its COMMON /O/ word list."""
    eng = forterp.run_source(src, dialect=dialect, target=forterp.NATIVE)
    return eng.commons[block]


def _prog(body):
    return "      PROGRAM T\n      COMMON /O/ N(8)\n" + body + "      END\n"


# ---- block IF -----------------------------------------------------------------------------
def test_block_if_then_runs_when_true():
    assert (
        _out(_prog("      N(1)=0\n      IF (1 .EQ. 1) THEN\n      N(1)=5\n      END IF\n"))[0] == 5
    )


def test_block_if_then_skipped_when_false():
    assert (
        _out(_prog("      N(1)=9\n      IF (1 .EQ. 2) THEN\n      N(1)=5\n      END IF\n"))[0] == 9
    )


def test_else_if_else_arms_are_mutually_exclusive():
    body = (
        "      DO 5 I=1,3\n"
        "        IF (I .EQ. 1) THEN\n"
        "          N(I)=10\n"
        "        ELSE IF (I .EQ. 2) THEN\n"
        "          N(I)=20\n"
        "        ELSE\n"
        "          N(I)=30\n"
        "        END IF\n"
        "    5 CONTINUE\n"
    )
    assert _out(_prog(body))[:3] == [10, 20, 30]


def test_nested_block_if():
    body = (
        "      I=2\n      J=3\n      N(1)=0\n"
        "      IF (I .EQ. 2) THEN\n"
        "        IF (J .EQ. 3) THEN\n"
        "          N(1)=7\n"
        "        ELSE\n"
        "          N(1)=5\n"
        "        ENDIF\n"
        "      ENDIF\n"
    )
    assert _out(_prog(body))[0] == 7


def test_block_if_inside_a_do_loop_keeps_the_loop():
    # a block IF whose arms jump forward must not disturb the enclosing DO (the lowered jumps
    # stay within the loop body, so the DO stack is preserved).
    body = (
        "      N(1)=0\n"
        "      DO 10 I=1,5\n"
        "        IF (MOD(I,2) .EQ. 0) THEN\n"
        "          N(1)=N(1)+I\n"
        "        END IF\n"
        "   10 CONTINUE\n"
    )
    assert _out(_prog(body), dialect=forterp.FORTRAN10)[0] == 6  # 2 + 4


def test_endif_one_word_and_two_word_spellings():
    one = _prog("      N(1)=0\n      IF(.TRUE.) THEN\n      N(1)=1\n      ENDIF\n")
    two = _prog("      N(1)=0\n      IF(.TRUE.) THEN\n      N(1)=1\n      END IF\n")
    assert _out(one)[0] == 1 and _out(two)[0] == 1


def test_goto_targets_a_labeled_end_if():
    # A GO TO may jump to a label on the END IF -- the construct's join point (a legal early exit
    # from the THEN block). Block-IF lowering must keep that source label on the synthesized join,
    # else the jump raises "jump to undefined statement label". Regression for FM255 / FM260.
    body = (
        "      N(1)=0\n"
        "      IF (1 .EQ. 1) THEN\n"
        "        N(1)=10\n"
        "        GO TO 50\n"
        "        N(1)=20\n"  # dead: the GO TO skips to the join
        "   50 END IF\n"
        "      N(2)=N(1)+1\n"
    )
    res = _out(_prog(body))
    assert res[0] == 10  # THEN entered; GO TO 50 jumped to the join, skipping N(1)=20
    assert res[1] == 11  # execution continued normally after the END IF join


# ---- DO WHILE (FORTRAN-10 dialect; not in strict ANSI F77) ---------------------------------
def test_do_while_accumulates():
    body = (
        "      N(1)=0\n      I=0\n      DO WHILE (I .LT. 5)\n"
        "      N(1)=N(1)+I\n      I=I+1\n      END DO\n"
    )
    assert _out(_prog(body), dialect=forterp.FORTRAN10)[0] == 10  # 0+1+2+3+4


def test_do_while_false_at_entry_runs_zero_times():
    body = "      N(1)=42\n      DO WHILE (1 .GT. 2)\n      N(1)=0\n      END DO\n"
    assert _out(_prog(body), dialect=forterp.FORTRAN10)[0] == 42


def test_do_while_not_available_in_strict_f77():
    # DO WHILE is a DEC/F90 extension, NOT ANSI X3.9-1978 -> the F77 dialect rejects it.
    with pytest.raises(forterp.ParseError):
        forterp.run_source(_prog("      DO WHILE (.TRUE.)\n      END DO\n"), dialect=forterp.F77)


# ---- SAVE (a no-op: forterp locals are already static) -------------------------------------
def test_save_is_accepted_and_is_a_noop():
    assert _out(_prog("      SAVE\n      N(1)=42\n"))[0] == 42
    assert _out(_prog("      SAVE N, I\n      N(1)=7\n"))[0] == 7


def test_save_as_a_variable_name_is_still_an_assignment():
    # `SAVE = expr` assigns the variable SAVE, it is not the SAVE statement.
    eng = forterp.run_source(
        "      PROGRAM T\n      COMMON /O/ N(8)\n      SAVE = 3\n      N(1) = SAVE\n      END\n",
        dialect=forterp.F77,
        target=forterp.NATIVE,
    )
    assert eng.commons["O"][0] == 3


# ---- dialect gating + the prebuilt interpreter ---------------------------------------------
def test_f66_rejects_block_if():
    with pytest.raises(forterp.ParseError):
        forterp.run_source(
            _prog("      IF (1 .EQ. 1) THEN\n      N(1)=5\n      END IF\n"), dialect=forterp.F66
        )


def test_prebuilt_f77_interpreter_runs_block_if():
    eng = forterp.f77.run_source(
        _prog("      N(1)=0\n      IF (.TRUE.) THEN\n      N(1)=99\n      END IF\n")
    )
    assert eng.commons["O"][0] == 99


def test_unterminated_block_if_is_a_clean_parse_error():
    with pytest.raises(forterp.ParseError):
        forterp.run_source(_prog("      IF (.TRUE.) THEN\n      N(1)=1\n"), dialect=forterp.F77)


# ---- generic intrinsics ---------------------------------------------------------------------
def _rprog(body):  # a REAL/COMPLEX result block
    return "      PROGRAM T\n      COMMON /O/ R(4)\n      COMPLEX Z\n" + body + "      END\n"


def test_f77_generic_log_and_log10_names():
    # F77's generic spellings LOG / LOG10 (F66 used ALOG / ALOG10).
    r = _out(_rprog("      R(1)=LOG(2.718281828459045)\n      R(2)=LOG10(1000.0)\n"))
    assert abs(r[0] - 1.0) < 1e-9 and abs(r[1] - 3.0) < 1e-9


def test_generic_sqrt_on_complex_dispatches_to_cmath():
    # SQRT of a complex argument resolves to the complex sqrt (CSQRT): sqrt(-4) = 2i.
    r = _out(
        _rprog("      Z=(-4.0,0.0)\n      Z=SQRT(Z)\n      R(1)=REAL(Z)\n      R(2)=AIMAG(Z)\n")
    )
    assert abs(r[0]) < 1e-9 and abs(r[1] - 2.0) < 1e-9


def test_generic_exp_on_complex():
    # EXP(i) = cos(1) + i*sin(1); generic EXP must not choke on a complex arg.
    r = _out(_rprog("      Z=(0.0,1.0)\n      Z=EXP(Z)\n      R(1)=REAL(Z)\n      R(2)=AIMAG(Z)\n"))
    assert abs(r[0] - 0.540302) < 1e-5 and abs(r[1] - 0.841471) < 1e-5


def test_generic_abs_is_polymorphic():
    # ABS already works for int / real / complex (|3-4i| = 5).
    r = _out(_rprog("      Z=(3.0,4.0)\n      R(1)=ABS(Z)\n      R(2)=ABS(-7.0)\n"))
    assert r[0] == 5.0 and r[1] == 7.0


# ---- INTRINSIC statement (a no-op: intrinsics already resolve by name) ----------------------
def test_intrinsic_statement_is_accepted_and_harmless():
    assert _out(_rprog("      INTRINSIC SQRT, SIN\n      R(1)=SQRT(9.0)\n"))[0] == 3.0


def test_intrinsic_statement_rejected_under_f66():
    with pytest.raises(forterp.ParseError):
        forterp.run_source("      PROGRAM T\n      INTRINSIC SIN\n      END\n", dialect=forterp.F66)


# ---- CHARACTER (Phase 2): declarations, assignment, concatenation, comparison, LEN ----------
def _cprog(body):
    # the tested value lands in COMMON /O/ R (read back as commons["O"][0]).
    return "      PROGRAM T\n      COMMON /O/ R\n" + body + "      END\n"


def test_character_assignment_blank_pads_to_declared_length():
    assert _out(_cprog("      CHARACTER R*5\n      R = 'HI'\n"))[0] == "HI   "


def test_character_assignment_truncates_when_too_long():
    assert _out(_cprog("      CHARACTER R*2\n      R = 'HELLO'\n"))[0] == "HE"


def test_character_concatenation():
    assert _out(_cprog("      CHARACTER R*6\n      R = 'AB' // 'CD'\n"))[0] == "ABCD  "


def test_character_equality_is_blank_padded():
    # 'HI   ' .EQ. 'HI' compares equal after F77 blank-padding to equal length.
    body = (
        "      CHARACTER S*5\n      INTEGER R\n"
        "      S='HI'\n      R=0\n      IF (S .EQ. 'HI') R=1\n"
    )
    assert _out(_cprog(body))[0] == 1


def test_character_lexical_ordering():
    body = (
        "      CHARACTER A*3, B*3\n      INTEGER R\n"
        "      A='ABC'\n      B='ABD'\n      R=0\n      IF (A .LT. B) R=1\n"
    )
    assert _out(_cprog(body))[0] == 1


def test_len_is_the_declared_length():
    assert (
        _out(_cprog("      CHARACTER S*7\n      INTEGER R\n      S='HI'\n      R=LEN(S)\n"))[0] == 7
    )


def test_implicit_character_length():
    # IMPLICIT CHARACTER*5 (R): R is implicitly CHARACTER*5, so the assignment blank-pads
    # to 5. This is the standard F77 FCVS audit-harness preamble (IMPLICIT CHARACTER*14 (C)).
    src = (
        "      PROGRAM T\n"
        "      IMPLICIT CHARACTER*5 (R)\n"
        "      COMMON /O/ R\n"
        "      R = 'HI'\n"
        "      END\n"
    )
    assert _out(src)[0] == "HI   "


def test_f77_zero_trip_do_and_final_index():
    # F77 (X3.9-1978 11.10): a DO whose count is <=0 runs ZERO times (F66/FORTRAN-10 run once),
    # and after a normal loop the index holds the value that exceeded the limit (11, not 10).
    zero = "      N(1)=0\n      DO 5 I=1,0\n      N(1)=N(1)+1\n    5 CONTINUE\n      N(2)=I\n"
    out = _out(_prog(zero))  # F77 dialect (the _out default)
    assert out[0] == 0 and out[1] == 1  # body ran 0x; index kept its start value
    fin = "      DO 6 I=1,10\n    6 CONTINUE\n      N(1)=I\n"
    assert _out(_prog(fin))[0] == 11
    # FORTRAN-10 stays one-trip with the last-value index (the F66 sentinel idiom)
    assert _out(_prog(zero), dialect=forterp.FORTRAN10)[0] == 1
    assert _out(_prog(fin), dialect=forterp.FORTRAN10)[0] == 10


def test_f77_zero_trip_inner_do_shared_terminal():
    # FM256: an outer DO and a zero-trip inner DO share terminal label 5. The inner loop
    # (5,1) never runs, so the shared terminal N(1)=N(1)+1 never executes (stays 0), but the
    # outer loop still runs fully: J=last outer value 10, I=post-loop 11 (X3.9-1978 11.10).
    body = (
        "      N(1)=0\n"
        "      DO 5 I=1,10\n"
        "      N(2)=I\n"
        "      DO 5 K=5,1\n"
        "      N(3)=K\n"
        "    5 N(1)=N(1)+1\n"
        "      N(4)=I\n"
        "      N(5)=K\n"
    )
    out = _out(_prog(body))
    assert out[0] == 0  # shared terminal (inner loop's) never executed
    assert out[1] == 10  # outer loop body ran 10x -> J = 10
    assert out[2] == 0  # inner body never ran -> N(3) untouched
    assert out[3] == 11  # outer index post-loop value
    assert out[4] == 5  # inner DO variable keeps its initial value (loop never ran)


def test_do_parameters_convert_to_integer_do_variable_type():
    # FM719 / X3.9-1978 11.10.2: an integer DO variable with real bounds converts the
    # parameters BEFORE the trip count -- DO I=6.7,9.325 truncates to 6,9,1 -> I=6,7,8,9
    # (sum 30, 4 trips), not the 3 a raw (9.325-6.7+1) real count would give.
    body = "      N(1)=0\n      DO 5 I=6.7,9.325\n      N(1)=N(1)+I\n    5 CONTINUE\n      N(2)=I\n"
    out = _out(_prog(body))
    assert out[0] == 30  # 6+7+8+9
    assert out[1] == 10  # post-loop index: 9 + 1


def test_do_label_optional_comma():
    # F77 allows a comma after the DO label: DO 5, I = 1, 3.
    body = "      N(1)=0\n      DO 5, I=1,3\n      N(1)=N(1)+I\n    5 CONTINUE\n"
    assert _out(_prog(body))[0] == 6


def test_parameter_logical_constant():
    # PARAMETER (LT = .TRUE.) -- a LOGICAL named constant, usable in a logical IF.
    src = (
        "      PROGRAM T\n"
        "      LOGICAL LT\n"
        "      PARAMETER (LT=.TRUE.)\n"
        "      COMMON /O/ N(8)\n"
        "      N(1)=0\n"
        "      IF (LT) N(1)=7\n"
        "      END\n"
    )
    assert _out(src)[0] == 7


def test_parameter_complex_constant():
    # PARAMETER (C = (3.0, 4.0)) -- a COMPLEX named constant.
    src = (
        "      PROGRAM T\n"
        "      COMPLEX C\n"
        "      PARAMETER (C=(3.0,4.0))\n"
        "      COMMON /O/ R\n"
        "      R=AIMAG(C)\n"
        "      END\n"
    )
    assert _out(src)[0] == 4.0


def test_character_array_elements():
    body = "      CHARACTER R*2, W(3)*2\n      W(2)='CD'\n      R=W(2)\n"
    assert _out(_cprog(body))[0] == "CD"


def test_character_declaration_rejected_without_the_character_type_dialect():
    for dia in (forterp.F66, forterp.FORTRAN10):
        with pytest.raises(forterp.ParseError):
            forterp.run_source(
                "      PROGRAM T\n      CHARACTER S*4\n      S='HI'\n      END\n",
                dialect=dia,
                target=forterp.NATIVE,
            )


def test_char_and_ichar_round_trip():
    assert _out(_cprog("      CHARACTER R*1\n      R = CHAR(65)\n"))[0] == "A"
    assert _out(_cprog("      INTEGER R\n      R = ICHAR('Z')\n"))[0] == 90


def test_index_is_one_based_and_zero_when_absent():
    assert _out(_cprog("      INTEGER R\n      R = INDEX('HELLO', 'LL')\n"))[0] == 3
    assert _out(_cprog("      INTEGER R\n      R = INDEX('HELLO', 'X')\n"))[0] == 0


def test_lexical_comparison_intrinsics():
    body = (
        "      INTEGER R\n      R = 0\n"
        "      IF (LGT('ABD','ABC')) R = R + 1\n"  # ABD > ABC -> +1
        "      IF (LLE('AB','AB')) R = R + 1\n"  # AB <= AB -> +1
        "      IF (.NOT. LLT('ABC','ABC')) R = R + 1\n"  # not (ABC < ABC) -> +1
    )
    assert _out(_cprog(body))[0] == 3


# ---- substrings S(i:j) (Phase 2c) -----------------------------------------------------------
def test_substring_read():
    assert _out(_cprog("      CHARACTER S*5, R*3\n      S='HELLO'\n      R=S(2:4)\n"))[0] == "ELL"


def test_substring_open_bounds():
    assert _out(_cprog("      CHARACTER S*5, R*3\n      S='HELLO'\n      R=S(:3)\n"))[0] == "HEL"
    assert _out(_cprog("      CHARACTER S*5, R*2\n      S='HELLO'\n      R=S(4:)\n"))[0] == "LO"


def test_substring_assignment_splices_in_place():
    assert _out(_cprog("      CHARACTER R*5\n      R='HELLO'\n      R(2:3)='XY'\n"))[0] == "HXYLO"


def test_substring_assignment_fits_rhs_to_the_slice_width():
    # RHS 'Z' is blank-padded to the 3-char slice; the rest of R is untouched.
    assert _out(_cprog("      CHARACTER R*5\n      R='AAAAA'\n      R(2:4)='Z'\n"))[0] == "AZ  A"


def test_array_element_substring_read():
    body = "      CHARACTER W(2)*5, R*2\n      W(1)='WORLD'\n      R=W(1)(2:3)\n"
    assert _out(_cprog(body))[0] == "OR"


def test_array_element_substring_assignment():
    body = "      CHARACTER R*3\n      R='ABC'\n      R(1:2)='XY'\n"
    assert _out(_cprog(body))[0] == "XYC"


# ---- A-format CHARACTER I/O (Phase 3) -------------------------------------------------------
def _run_io(src, stdin=""):
    return forterp.run_source(
        src, dialect=forterp.F77, target=forterp.NATIVE, readline=io.StringIO(stdin).readline
    )


def test_a_format_writes_a_character():
    eng = _run_io(
        _cprog("      CHARACTER S*5\n      S='HI'\n      WRITE(6,10) S\n   10 FORMAT(A5)\n")
    )
    assert "".join(eng.out).strip() == "HI"  # 'HI   ' (A5)


def test_list_directed_write_and_read():
    # F77 §12: list-directed I/O (READ/WRITE with * for the format).
    assert "42" in "".join(
        _run_io("      PROGRAM T\n      I=42\n      WRITE(6,*) I\n      END\n").out
    )
    src = "      PROGRAM T\n      COMMON /O/ N(8)\n      READ(5,*) N(1)\n      END\n"
    assert _run_io(src, stdin="42\n").commons["O"][0] == 42


def test_blanks_within_a_dotted_operator():
    # Fixed-form blanks are insignificant: "C10VK. NE. 'YES'" reads as .NE. (FCVS FM915/FM920).
    src = (
        "      PROGRAM T\n      CHARACTER C10VK*3\n      COMMON /O/ N(8)\n"
        "      C10VK='NO'\n      N(1)=0\n      IF (C10VK. NE. 'YES') N(1)=4\n      END\n"
    )
    assert _out(src)[0] == 4


def test_assumed_size_array_dummy():
    # F77 assumed-size dummy array A(*): the last upper bound is the actual's; element reads
    # alias the actual (column-major linidx never needs the last dim's extent).
    src = (
        "      PROGRAM T\n      COMMON /O/ N(8)\n      DIMENSION A(5)\n"
        "      DO 1 I=1,5\n    1 A(I)=I*10\n      CALL S(A,N(1))\n      END\n"
        "      SUBROUTINE S(A, R)\n      DIMENSION A(*)\n      R=A(3)\n      RETURN\n      END\n"
    )
    assert _out(src)[0] == 30


def test_character_data_initialization():
    # DATA initialises a CHARACTER scalar to the blank-padded string (not a packed Hollerith word).
    src = (
        "      PROGRAM T\n      CHARACTER R*5\n      COMMON /O/ R\n      DATA R /'HI'/\n      END\n"
    )
    assert _out(src)[0] == "HI   "


def test_data_substring_target():
    # DATA into a CHARACTER substring splices into the base, leaving the rest untouched.
    src = (
        "      PROGRAM T\n      CHARACTER R*5\n      COMMON /O/ R\n"
        "      DATA R /'.....'/\n      DATA R(2:3) /'XY'/\n      END\n"
    )
    assert _out(src)[0] == ".XY.."


def test_f77_array_bound_slash_is_division():
    # Under F77 the only array-bound separator is ':'; a '/' in a bound is ordinary division,
    # so A(6/3:9) has lower bound 2 (the DEC A(lo/hi) bound form is FORTRAN-10 only).
    src = (
        "      PROGRAM T\n      DIMENSION A(6/3:9)\n      COMMON /O/ N(8)\n"
        "      A(2)=1.0\n      A(9)=2.0\n      N(1)=7\n      END\n"
    )
    assert _out(src)[0] == 7


def test_character_parametrised_length():
    # F77 §5.1: CHARACTER*(expr) -- a parenthesised integer-constant length (here a PARAMETER).
    src = (
        "      PROGRAM T\n      PARAMETER (LPI=5)\n      CHARACTER*(LPI) S\n"
        "      COMMON /O/ S\n      S='HI'\n      END\n"
    )
    assert _out(src)[0] == "HI   "


def test_blank_common_slash_forms_parse():
    # The three // blank-common spellings FM302 exercises: a leading //, a // between member
    # groups, and a comma before a // specifier. Layout/value semantics are checked by the
    # FCVS FM302 routine; here we just guard that the F77 // (concat) token doesn't break them.
    src = (
        "      PROGRAM T\n      COMMON //A\n      COMMON RVCN01//B\n"
        "      COMMON D, //E\n      A=1.0\n      END\n"
    )
    assert forterp.run_source(src, dialect=forterp.F77, target=forterp.NATIVE) is not None


def test_eqv_and_neqv_operators():
    # F77 §6.6: logical equivalence .EQV. and non-equivalence .NEQV.
    eqv = (
        "      PROGRAM T\n      LOGICAL L\n      COMMON /O/ N(8)\n"
        "      L = .TRUE. .EQV. .FALSE.\n      N(1)=0\n      IF (.NOT. L) N(1)=5\n      END\n"
    )
    assert _out(eqv)[0] == 5
    neqv = (
        "      PROGRAM T\n      LOGICAL L\n      COMMON /O/ N(8)\n"
        "      L = .TRUE. .NEQV. .FALSE.\n      N(1)=0\n      IF (L) N(1)=9\n      END\n"
    )
    assert _out(neqv)[0] == 9


def test_keyword_io_control_list():
    # F77 §12.8: a READ/WRITE keyword control list -- UNIT=/FMT= route to the unit & format.
    eng = _run_io(
        "      PROGRAM T\n      I=7\n      WRITE(UNIT=6,FMT=10) I\n"
        "   10 FORMAT(1H ,I3)\n      END\n"
    )
    assert "".join(eng.out).strip() == "7"
    src = (
        "      PROGRAM T\n      COMMON /O/ N(8)\n      READ(UNIT=5,FMT=10) N(1)\n"
        "   10 FORMAT(I3)\n      END\n"
    )
    assert _run_io(src, stdin=" 42\n").commons["O"][0] == 42


def test_widthless_a_uses_item_length_round_trip():
    # F77 13.5.11: a widthless A uses the list item's length, so ten CHARACTER*1 values take ten
    # columns (not 10x the default width 5) and round-trip through a scratch file.
    src = (
        "      PROGRAM T\n      CHARACTER C(10)*1, D(10)*1\n      COMMON /O/ N(8)\n"
        "      DO 1 I=1,10\n    1 C(I)=CHAR(48+I-1)\n"
        "      WRITE(7,9)(C(I),I=1,10)\n    9 FORMAT(10A)\n      REWIND 7\n"
        "      READ(7,9)(D(I),I=1,10)\n"
        "      K=0\n      DO 2 I=1,10\n      IF (C(I).EQ.D(I)) K=K+1\n    2 CONTINUE\n"
        "      N(1)=K\n      END\n"
    )
    assert _out(src)[0] == 10


def test_widthless_a_reads_items_of_differing_lengths():
    # FM402 / F77 13.5.11: a repeated widthless A (4A) reads each list item using its OWN
    # declared length -- here 1, 2, 5, 10 columns from one record -- not a fixed width.
    src = (
        "      PROGRAM T\n"
        "      CHARACTER A*1, B*2, C*5, D*10\n      COMMON /O/ N(8)\n"
        "      A='?'\n      B='??'\n      C='?????'\n      D='??????????'\n"
        "      WRITE(7,9)\n    9 FORMAT('ABCDEFGHIJKLMNOPQR')\n      REWIND 7\n"
        "      READ(7,8) A, B, C, D\n    8 FORMAT(4A)\n"
        "      N(1)=0\n"
        "      IF (A.EQ.'A') N(1)=N(1)+1\n"
        "      IF (B.EQ.'BC') N(1)=N(1)+1\n"
        "      IF (C.EQ.'DEFGH') N(1)=N(1)+1\n"
        "      IF (D.EQ.'IJKLMNOPQR') N(1)=N(1)+1\n"
        "      END\n"
    )
    assert _out(src)[0] == 4  # all four items read their own declared length


def _iwrite(fmt, value):
    """Internal-file WRITE of `value` under `fmt` into a CHARACTER*10; return the record."""
    src = (
        "      PROGRAM T\n      COMMON /O/ S\n      CHARACTER S*10\n"
        f"      WRITE(S,10) {value}\n   10 FORMAT({fmt})\n      END\n"
    )
    return forterp.run_source(src, dialect=forterp.F77, target=forterp.NATIVE).commons["O"][0]


def test_f_format_value_rounding_to_zero_drops_the_minus_sign():
    # FM406: F4.1 of -0.0001 rounds to zero, which must print without a minus sign.
    assert _iwrite("F4.1", "-0.0001") == " 0.0      "


def test_e_format_drops_leading_zero_to_fit_a_narrow_field():
    # FM406: E9.4 of 2345.0 is "0.2345E+04" (10 cols) but the field is 9 -- the optional
    # leading zero is dropped to fit (".2345E+04"), not overflowed to asterisks.
    assert _iwrite("E9.4", "2345.0") == ".2345E+04 "


def test_e_format_explicit_exponent_width():
    # FM406 / FM912: Ew.dEe gives the exponent exactly e digits and always keeps the letter.
    assert _iwrite("E8.4E1", "2345.0") == ".2345E+4  "


def test_blank_null_default_on_width_d_numeric_read():
    # Regression: under F77 (and FORTRAN-10) a width'd numeric field's blanks default to NULL
    # (ignored), so reading '5' padded to an I5 field yields 5, not 50000 (the F66 blanks-as-zero).
    src = (
        "      PROGRAM T\n      COMMON /O/ N(8)\n      CHARACTER C*5\n"
        "      C='5'\n      READ(C,10) N(1)\n   10 FORMAT(I5)\n      END\n"
    )
    eng = forterp.run_source(src, dialect=forterp.F77, target=forterp.NATIVE)
    assert eng.commons["O"][0] == 5


def test_iw_m_minimum_digits():
    # FM912 / 13.5.9.1: Iw.m prints at least m digits, zero-filled (I5.3 of 5 -> '  005').
    assert _iwrite("I5.3", "5") == "  005     "


def test_sp_ss_sign_control():
    # FM912 / 13.5.6: SP forces a + on a non-negative; SS suppresses it again.
    assert _iwrite("SP,I5,SS,I5", "5, 7") == "   +5    7"


def test_colon_terminates_format_when_list_exhausted():
    # FM912 / 13.3: the colon stops format control once the io-list is spent, so the
    # trailing literal is not emitted.
    assert _iwrite("I3,:,'XX'", "7") == "  7       "


def test_tl_tr_relative_tabs():
    # FM912 / 13.5.4: TR advances the cursor (gap blank-filled), TL backs it up to overwrite.
    # 'AB' (cols 1-2), TR3 -> col 6, 'C' (col 6), TL2 -> col 4, 'Z' (col 4): "AB  ZC".
    assert _iwrite("'AB',TR3,'C',TL2,'Z'", "") == "AB  ZC    "


def test_read_into_a_character_substring_target():
    # FM912: a CHARACTER substring lvalue as an I/O-list item must be written back, not
    # dropped -- READ A5 into S(1:5) splices into the base, leaving the rest unchanged.
    src = (
        "      PROGRAM T\n      COMMON /O/ S\n      CHARACTER S*10, T*10\n"
        "      S='..........'\n      T='HELLOworld'\n"
        "      READ(T,9) S(1:5)\n    9 FORMAT(A5)\n      END\n"
    )
    eng = forterp.run_source(src, dialect=forterp.F77, target=forterp.NATIVE)
    assert eng.commons["O"][0] == "HELLO....."


def test_widthless_a_writes_full_character_value():
    # F77 §13.5.11: a widthless A takes the list item's CHARACTER length (here 5). Strict
    # F66 rejects a widthless descriptor; the relaxation is gated on the CHARACTER type.
    eng = _run_io(
        _cprog("      CHARACTER S*5\n      S='HI'\n      WRITE(6,10) S\n   10 FORMAT(A)\n")
    )
    assert "".join(eng.out).strip() == "HI"


def test_sequential_scratch_file_round_trip():
    # An unconnected unit defaults to a sequential scratch file: WRITE a record, REWIND,
    # and READ it back (the FCVS FM10x tape/disk routines rely on this).
    src = (
        "      PROGRAM T\n      COMMON /O/ N(8)\n"
        "      WRITE(7,10) 42\n   10 FORMAT(I5)\n      REWIND 7\n"
        "      READ(7,10) K\n      N(1)=K\n      END\n"
    )
    assert _out(src)[0] == 42


def test_formatted_file_slash_record_break_round_trip():
    # A formatted WRITE with / (record break) round-trips through a sequential file: the
    # rendered text records preserve record boundaries, and the read splits the format at /.
    src = (
        "      PROGRAM T\n      COMMON /O/ N(8)\n"
        "      WRITE(7,10) 11, 22\n   10 FORMAT(I3/I3)\n      REWIND 7\n"
        "      READ(7,20) I, J\n   20 FORMAT(I3/I3)\n      N(1)=I\n      N(2)=J\n      END\n"
    )
    out = _out(src)
    assert out[0] == 11 and out[1] == 22


def test_formatted_file_read_reversion():
    # Read-side FORMAT reversion (X3.9-1978 13.3): a format shorter than the I/O list re-scans
    # and advances a record. M is written under (2I3) -> 2 records; K reads it back the same way.
    src = (
        "      PROGRAM T\n      COMMON /O/ N(8)\n      DIMENSION M(4),K(4)\n"
        "      M(1)=7\n      M(2)=8\n      M(3)=9\n      M(4)=5\n"
        "      WRITE(7,10) M\n   10 FORMAT(2I3)\n      REWIND 7\n"
        "      READ(7,10) K\n      DO 1 I=1,4\n    1 N(I)=K(I)\n      END\n"
    )
    assert _out(src)[:4] == [7, 8, 9, 5]


def test_a_format_reads_a_character():
    src = _cprog("      CHARACTER R*5\n      READ(5,10) R\n   10 FORMAT(A5)\n")
    assert _run_io(src, stdin="WORLD\n").commons["O"][0] == "WORLD"


def test_a_input_takes_rightmost_when_field_wider_than_var():
    src = _cprog("      CHARACTER R*2\n      READ(5,10) R\n   10 FORMAT(A5)\n")
    assert _run_io(src, stdin="HELLO\n").commons["O"][0] == "LO"


def test_a_output_right_justifies_when_field_wider_than_value():
    # 1H supplies the carriage-control char (consumed) so the A5 field's leading blanks survive.
    body = "      CHARACTER S*2\n      S='HI'\n      WRITE(6,10) S\n   10 FORMAT(1H ,A5)\n"
    assert "".join(_run_io(_cprog(body)).out).rstrip("\n").endswith("   HI")


# ---- internal files: READ/WRITE to a CHARACTER variable (Phase 3) ---------------------------
def test_internal_write_formats_into_a_character_var():
    body = (
        "      CHARACTER R*10\n      INTEGER N\n      N=42\n      WRITE(R,10) N\n   10 FORMAT(I5)\n"
    )
    assert _out(_cprog(body))[0] == "   42     "  # I5 of 42, blank-padded to length 10


def test_internal_read_parses_from_a_character_var():
    body = (
        "      CHARACTER S*10\n      INTEGER R\n"
        "      S='  123'\n      READ(S,10) R\n   10 FORMAT(I5)\n"
    )
    assert _out(_cprog(body))[0] == 123


def test_internal_file_round_trip():
    body = (
        "      CHARACTER S*8\n      INTEGER N, R\n      N=7\n"
        "      WRITE(S,10) N\n      READ(S,10) R\n   10 FORMAT(I4)\n"
    )
    assert _out(_cprog(body))[0] == 7


def test_internal_file_character_array_write():
    # FM909 / X3.9-1978 12.2.2: a CHARACTER ARRAY is an internal file whose ELEMENTS are the
    # records. A WRITE with FORMAT reversion (two values, one I5) fills consecutive elements.
    src = (
        "      PROGRAM T\n      COMMON /O/ S\n      CHARACTER S*10, A(2)*5\n"
        "      WRITE(A,10) 42, 99\n   10 FORMAT(I5)\n      S=A(1)//A(2)\n      END\n"
    )
    eng = forterp.run_source(src, dialect=forterp.F77, target=forterp.NATIVE)
    assert eng.commons["O"][0] == "   42   99"


def test_internal_write_mixed_a_and_i():
    body = (
        "      CHARACTER R*12, W*5\n      INTEGER K\n"
        "      W='ITEM'\n      K=9\n      WRITE(R,10) W, K\n   10 FORMAT(A5,I3)\n"
    )
    assert _out(_cprog(body))[0] == "ITEM   9    "


# ---- INQUIRE (Phase 3) ----------------------------------------------------------------------
def test_inquire_exist_by_file(tmp_path):
    (tmp_path / "THERE.DAT").write_text("hi")
    root = str(tmp_path)
    yes = forterp.run_source(
        _cprog("      LOGICAL R\n      INQUIRE(FILE='THERE.DAT', EXIST=R)\n"),
        dialect=forterp.F77,
        target=forterp.NATIVE,
        root=root,
    )
    no = forterp.run_source(
        _cprog("      LOGICAL R\n      INQUIRE(FILE='GONE.DAT', EXIST=R)\n"),
        dialect=forterp.F77,
        target=forterp.NATIVE,
        root=root,
    )
    assert yes.commons["O"][0] and not no.commons["O"][0]


def test_inquire_opened_is_false_for_an_unconnected_unit():
    assert not _out(_cprog("      LOGICAL R\n      INQUIRE(UNIT=9, OPENED=R)\n"))[0]


def test_inquire_number_echoes_the_unit():
    assert _out(_cprog("      INTEGER R\n      INQUIRE(UNIT=7, NUMBER=R)\n"))[0] == 7


def test_inquire_exist_true_for_a_connected_direct_file(tmp_path):
    # A DIRECT-access file just OPENed (modeled in memory, no disk backing yet) must still
    # report EXIST=.TRUE. -- a connected file exists (FM921, X3.9-1978 12.10.2).
    src = _cprog(
        "      LOGICAL R\n"
        "      OPEN(UNIT=8, FILE='SCRATCH.DAT', ACCESS='DIRECT',\n"
        "     1     RECL=40, FORM='UNFORMATTED')\n"
        "      INQUIRE(FILE='SCRATCH.DAT', EXIST=R)\n"
    )
    eng = forterp.run_source(src, dialect=forterp.F77, target=forterp.NATIVE, root=str(tmp_path))
    assert eng.commons["O"][0]


def test_direct_access_records_survive_close_and_reopen(tmp_path):
    # A direct-access file's records persist on CLOSE and reload on a STATUS='OLD' reopen
    # (FM912): write two records, close, reopen, read one back.
    src = _cprog(
        "      INTEGER R\n"
        "      OPEN(UNIT=8, FILE='DA.TMP', ACCESS='DIRECT', RECL=20,\n"
        "     1     FORM='FORMATTED', STATUS='NEW')\n"
        "      WRITE(UNIT=8, REC=1, FMT=10) 111\n"
        "      WRITE(UNIT=8, REC=2, FMT=10) 222\n"
        "   10 FORMAT(I5)\n"
        "      CLOSE(UNIT=8)\n"
        "      OPEN(UNIT=8, FILE='DA.TMP', ACCESS='DIRECT', RECL=20,\n"
        "     1     FORM='FORMATTED', STATUS='OLD')\n"
        "      READ(UNIT=8, REC=2, FMT=10) R\n"
    )
    eng = forterp.run_source(src, dialect=forterp.F77, target=forterp.NATIVE, root=str(tmp_path))
    assert eng.commons["O"][0] == 222


def test_direct_access_slash_format_writes_consecutive_records(tmp_path):
    # A '/' in the FORMAT of a direct-access WRITE writes consecutive records (FM912 test 5):
    # WRITE REC=1 with two format records fills records 1 and 2, so NEXTREC advances to 3.
    src = _cprog(
        "      INTEGER R\n"
        "      OPEN(UNIT=8, FILE='DA2.TMP', ACCESS='DIRECT', RECL=20,\n"
        "     1     FORM='FORMATTED', STATUS='NEW')\n"
        "      WRITE(UNIT=8, REC=1, FMT=10) 11, 22\n"
        "   10 FORMAT(I5,/,I5)\n"
        "      INQUIRE(UNIT=8, NEXTREC=R)\n"
    )
    eng = forterp.run_source(src, dialect=forterp.F77, target=forterp.NATIVE, root=str(tmp_path))
    assert eng.commons["O"][0] == 3  # records 1 and 2 written -> next is 3


# ---- procedure / statement-function semantics ---------------------------------------------
def test_intrinsic_name_passed_as_actual_argument():
    # IABS, declared INTRINSIC, passed to a dummy procedure and called through it (FM317/328,
    # X3.9-1978 15.10). The dummy NF must dispatch to the library IABS, not the intrinsic NINT.
    src = (
        "      PROGRAM T\n      COMMON /O/ R\n      INTEGER R, FF\n"
        "      INTRINSIC IABS\n      EXTERNAL FF\n"
        "      R = FF(IABS, -7)\n      END\n"
        "      INTEGER FUNCTION FF(NF, K)\n      FF = NF(K) + 1\n      RETURN\n      END\n"
    )
    eng = forterp.run_source(src, dialect=forterp.F77, target=forterp.NATIVE)
    assert eng.commons["O"][0] == 8  # IABS(-7) + 1


def test_integer_statement_function_truncates_its_real_result():
    # An INTEGER-named statement function converts its real body value to INTEGER (FM351,
    # X3.9-1978 15.4.1): ISF(4.7) = INT(4.7) = 4, not 4.7 leaking through to the caller.
    body = "      INTEGER R, ISF\n      ISF(X) = X\n      R = ISF(4.7)\n"
    assert _out(_cprog(body))[0] == 4


def test_data_parameter_repeat_count_and_character_parameter_value():
    # FM500: a DATA `n*value` repeat count may be a PARAMETER (not a literal), and a CHARACTER
    # PARAMETER used as a DATA value is kept as text (fit to the target), not packed as Hollerith.
    src = (
        "      PROGRAM T\n      COMMON /O/ N(8)\n"
        "      INTEGER A(3)\n      CHARACTER C(2)*1\n"
        "      PARAMETER (NP=3, CX='X')\n"
        "      DATA A /NP*7/\n      DATA C /2*CX/\n"
        "      N(1)=A(1)+A(2)+A(3)\n"
        "      N(2)=0\n      IF (C(1).EQ.'X' .AND. C(2).EQ.'X') N(2)=1\n"
        "      END\n"
    )
    out = _out(src)
    assert out[0] == 21  # 3*7 -- the PARAMETER repeat count NP resolved
    assert out[1] == 1  # CHARACTER PARAMETER value kept as 'X', not a packed word


def test_concat_operator_only_tokenized_under_character_type():
    # // is the concat operator only when CHARACTER is in play; FORTRAN-10 must not see it.
    src = "      PROGRAM T\n      COMMON /O/ S\n      CHARACTER S*4\n      S='A'//'B'\n      END\n"
    with pytest.raises(forterp.ParseError):
        forterp.run_source(src, dialect=forterp.FORTRAN10, target=forterp.NATIVE)
