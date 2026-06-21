"""Error & exception handling: malformed source raises a clean ParseError (never a Python
traceback), and the CLI turns a runtime fault into a `?` diagnostic with a nonzero exit
rather than dumping a stack. Regression for the error-handling review."""

import os
import tempfile

import pytest

import forterp
from forterp.cli import main


def _parse_raises(src, dialect=forterp.FORTRAN10):
    with pytest.raises(forterp.ParseError):
        forterp.parse_source(src, dialect=dialect)


def _cli_fails_cleanly(capsys, text, args=()):
    """Run `text` through the CLI; assert it exits nonzero with a ?-diagnostic on stderr and
    NO raw Python traceback. Returns stderr."""
    with tempfile.NamedTemporaryFile("w", suffix=".FOR", delete=False) as f:
        f.write(text)
        path = f.name
    try:
        rc = main([*args, path])
    finally:
        os.unlink(path)
    err = capsys.readouterr().err
    assert rc == 1, f"expected nonzero exit, got {rc}"
    assert "Traceback" not in err, f"raw traceback leaked:\n{err}"
    assert "?" in err, f"expected a ?-diagnostic, got:\n{err}"
    return err


# ---- source-level faults become ParseError, not a Python exception --------
def test_constant_division_by_zero_is_a_parse_error():
    _parse_raises("      PROGRAM T\n      PARAMETER (N=1/0)\n      I=N\n      END\n")


def test_constant_type_mismatch_is_a_parse_error():
    _parse_raises("      PROGRAM T\n      PARAMETER (N='AB'+1)\n      END\n")


def test_implicit_multichar_range_is_a_parse_error():
    _parse_raises("      PROGRAM T\n      IMPLICIT INTEGER(AB-C)\n      END\n")


# ---- runtime faults reach the user as a `?` diagnostic, never a traceback ----
def test_undefined_subroutine_is_a_clean_cli_error(capsys):
    _cli_fails_cleanly(capsys, "      PROGRAM T\n      CALL NOPE\n      END\n")


def test_jump_to_undefined_label_is_clean(capsys):
    _cli_fails_cleanly(capsys, "      PROGRAM T\n      GO TO 999\n      END\n")


def test_missing_format_label_is_clean(capsys):
    _cli_fails_cleanly(capsys, "      PROGRAM T\n      WRITE(6,900)\n      END\n")


def test_undefined_do_terminal_label_is_clean(capsys):
    _cli_fails_cleanly(capsys, "      PROGRAM T\n      DO 50 I=1,3\n      K=I\n      END\n")


def test_unknown_program_name_is_clean(capsys):
    _cli_fails_cleanly(capsys, "      PROGRAM T\n      END\n", args=("--program", "NOPE"))


def test_library_builtin_wrong_arg_count_is_clean(capsys):
    # CALL TIME with no arguments is a clean runtime error, not a raw IndexError.
    err = _cli_fails_cleanly(
        capsys, "      PROGRAM T\n      CALL TIME\n      END\n", args=("--std", "fortran10")
    )
    assert "TIME" in err


def test_huge_array_allocation_is_a_clean_error(capsys):
    # A hostile or accidental huge DIMENSION raises a clean error (the max_array_words
    # cap), not an out-of-memory crash.
    err = _cli_fails_cleanly(
        capsys,
        "      PROGRAM T\n      DIMENSION A(2000000000)\n      A(1)=1\n      END\n",
        args=("--std", "fortran10"),
    )
    assert "exceeds" in err
