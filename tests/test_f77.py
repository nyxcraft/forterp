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


def test_widthless_a_writes_full_character_value():
    # F77 §13.5.11: a widthless A takes the list item's CHARACTER length (here 5). Strict
    # F66 rejects a widthless descriptor; the relaxation is gated on the CHARACTER type.
    eng = _run_io(
        _cprog("      CHARACTER S*5\n      S='HI'\n      WRITE(6,10) S\n   10 FORMAT(A)\n")
    )
    assert "".join(eng.out).strip() == "HI"


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


def test_concat_operator_only_tokenized_under_character_type():
    # // is the concat operator only when CHARACTER is in play; FORTRAN-10 must not see it.
    src = "      PROGRAM T\n      COMMON /O/ S\n      CHARACTER S*4\n      S='A'//'B'\n      END\n"
    with pytest.raises(forterp.ParseError):
        forterp.run_source(src, dialect=forterp.FORTRAN10, target=forterp.NATIVE)
