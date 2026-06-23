"""Smoke tests for the console entry points (forterp.cli): pyf66 / pyfortran10 / forterp.

They pin that the commands run a file, route program output to stdout, and that the
dialect boundary is visible at the CLI (pyf66 rejects a DEC feature pyfortran10 runs)."""

import io
import os
import tempfile

import pytest

from forterp.cli import f10_main, f66_main, main

# strict ANSI F66: Hollerith FORMAT, no DEC features
HELLO_F66 = "      PROGRAM T\n      WRITE(6,10)\n   10 FORMAT(15H HELLO FROM F66)\n      END\n"
# DEC FORTRAN-10: uses IMPLICIT (a FORTRAN-10 statement, rejected under strict F66)
DEC = (
    "      PROGRAM T\n      IMPLICIT INTEGER(A-Z)\n"
    "      WRITE(6,10)\n   10 FORMAT(15H HELLO FROM F10)\n      END\n"
)


def _src(text):
    with tempfile.NamedTemporaryFile("w", suffix=".FOR", delete=False) as f:
        f.write(text)
        return f.name


def test_pyf66_runs_strict_f66(capsys):
    p = _src(HELLO_F66)
    try:
        rc = f66_main([p])
    finally:
        os.unlink(p)
    assert rc == 0
    assert "HELLO FROM F66" in capsys.readouterr().out


def test_pyfortran10_accepts_dec_feature(capsys):
    p = _src(DEC)
    try:
        rc = f10_main([p])
    finally:
        os.unlink(p)
    assert rc == 0
    assert "HELLO FROM F10" in capsys.readouterr().out


def test_pyf66_rejects_dec_feature(capsys):
    p = _src(DEC)
    try:
        rc = f66_main([p])
    finally:
        os.unlink(p)
    cap = capsys.readouterr()
    assert rc == 1  # nonzero exit on parse error
    assert "HELLO FROM F10" not in cap.out  # the program did not run
    assert "IMPLICIT" in cap.err  # the diagnostic went to stderr


def test_general_driver_std_selects_dialect(capsys):
    p = _src(DEC)
    try:
        assert main(["--std", "fortran10", p]) == 0  # DEC dialect accepts IMPLICIT
        assert "HELLO FROM F10" in capsys.readouterr().out
        assert main(["--std", "f66", p]) == 1  # strict F66 rejects it
    finally:
        os.unlink(p)


def test_check_lists_all_diagnostics_without_running(capsys):
    # --check = compile-check: parse, list every %FTN diagnostic, do NOT run.
    p = _src(DEC)  # uses IMPLICIT (a FORTRAN-10 statement)
    try:
        rc = f66_main(["--check", p])
    finally:
        os.unlink(p)
    cap = capsys.readouterr()
    assert rc == 1
    assert "error(s)" in cap.err and "IMPLICIT" in cap.err  # diagnostic listed
    assert "HELLO FROM F10" not in cap.out  # nothing ran


def test_bad_input_field_reports_clean_error_not_traceback(monkeypatch, capsys):
    # a bad numeric field with no ERR= halts with a clean ?-error, not a Python traceback
    monkeypatch.setattr("sys.stdin", io.StringIO("xyz\n"))
    p = _src("      PROGRAM T\n      READ(5,10) N\n   10 FORMAT(I5)\n      END\n")
    try:
        rc = f10_main([p])
    finally:
        os.unlink(p)
    err = capsys.readouterr().err
    assert rc == 1
    assert "?" in err  # a FORTRAN-style ? diagnostic
    assert "Traceback" not in err  # not a raw Python traceback


def test_read_with_end_branches_at_stream_eof(monkeypatch, capsys):
    # A formatted READ(...,END=) past end-of-input must branch to the END= label, not spin
    # forever re-reading empty records. Regression: terminal EOF was detected only via an
    # in-band CONTROL-Z, never via readline() returning "" (real stream EOF), so a read
    # loop over stdin hung. (The 1971 LIFE.FOR surfaced this.)
    monkeypatch.setattr("sys.stdin", io.StringIO("ABC\n"))  # one record, then EOF
    src = (
        "      PROGRAM T\n      INTEGER R(3)\n    5 READ(5,9,END=11) R\n"
        "    9 FORMAT(3A1)\n      GO TO 5\n   11 WRITE(6,12)\n"
        "   12 FORMAT(13H REACHED EOF.)\n      END\n"
    )
    p = _src(src)
    try:
        rc = f10_main([p])
    finally:
        os.unlink(p)
    assert rc == 0
    assert "REACHED EOF" in capsys.readouterr().out


def test_multiple_files_link_by_unit_name(capsys):
    # Several source files on the command line are concatenated and linked by unit name,
    # like `f77 main.f lib.f`: a main program in one file calls a SUBROUTINE in another.
    main_src = "      PROGRAM T\n      CALL GREET\n      END\n"
    lib_src = (
        "      SUBROUTINE GREET\n      WRITE(6,10)\n   10 FORMAT(13H HELLO LINKED)\n      END\n"
    )
    pm, pl = _src(main_src), _src(lib_src)
    try:
        rc = f66_main([pm, pl])
    finally:
        os.unlink(pm)
        os.unlink(pl)
    assert rc == 0
    assert "HELLO LINKED" in capsys.readouterr().out


def test_check_reports_ok_on_clean_source(capsys):
    p = _src(HELLO_F66)  # strict-F66-clean (Hollerith FORMAT)
    try:
        rc = f66_main(["--check", p])
    finally:
        os.unlink(p)
    assert rc == 0
    assert "unit(s) OK" in capsys.readouterr().out


# A flat host-routine module dropped in beside FORTRAN source -- discovered and registered
# by basename, no registry/__init__ needed.
_PY_BUILTIN = (
    "from forterp.hostlib import builtin, INT\n\n\n"
    "@builtin('IDIST', args=(INT, INT))\n"
    "def idist(a, b):\n"
    "    return abs(a - b)\n"
)
_CALLS_IDIST = (
    "      PROGRAM T\n      WRITE(6,10) IDIST(3,7), IDIST(10,2)\n"
    "   10 FORMAT(' IDIST:', 2I5)\n      END\n"
)


def _pyfile(text):
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(text)
        return f.name


def test_py_argument_registers_host_routines(capsys):
    pf, src = _pyfile(_PY_BUILTIN), _src(_CALLS_IDIST)
    try:
        rc = f10_main([pf, src])  # the .py provides IDIST; the .FOR calls it
    finally:
        os.unlink(pf)
        os.unlink(src)
    assert rc == 0
    assert "IDIST:    4    8" in capsys.readouterr().out


def test_py_module_without_fortran_is_an_error(capsys):
    pf = _pyfile(_PY_BUILTIN)
    try:
        with pytest.raises(SystemExit):  # argparse error: nothing to run
            f10_main([pf])
    finally:
        os.unlink(pf)
    assert "no FORTRAN source" in capsys.readouterr().err


# ---- the default terminal-echo control (run_source installs it on a real tty) --------------
def test_default_terminal_echo_flips_and_restores_on_a_tty():
    import pty
    import termios

    from forterp.runtime import default_terminal_echo

    _, slave = pty.openpty()  # a real tty
    set_echo, restore = default_terminal_echo(slave)
    assert set_echo is not None
    assert termios.tcgetattr(slave)[3] & termios.ECHO  # a fresh tty echoes
    set_echo(False)  # ECHOFF
    assert not (termios.tcgetattr(slave)[3] & termios.ECHO)  # ECHO bit really cleared
    set_echo(True)  # ECHOON
    assert termios.tcgetattr(slave)[3] & termios.ECHO
    set_echo(False)  # a program that forgot to ECHOON before exit
    restore()  # run_source calls this at the end of the run
    assert termios.tcgetattr(slave)[3] & termios.ECHO  # restored to the entry state


def test_default_terminal_echo_is_a_noop_off_a_terminal():
    import os

    from forterp.runtime import default_terminal_echo

    r, _ = os.pipe()  # a pipe fd is not a tty
    set_echo, restore = default_terminal_echo(r)
    assert set_echo is None and restore is None  # clean no-op; run_source skips it
