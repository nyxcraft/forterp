"""FORTRAN 77 dialect -- Phase 1: block IF / DO WHILE / SAVE.

These exercise the structured-control lowering (the parser emits BlockIf/ElseIf/.../EndDo
markers; parser._lower_structured rewrites them to the engine's flat label+GOTO form). Run
under the F77 dialect (NATIVE target) unless a test says otherwise. CHARACTER and the F77
I/O set are not implemented yet (a later phase)."""

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
