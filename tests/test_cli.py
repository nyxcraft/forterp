"""Smoke tests for the console entry points (forterp.cli): pyf66 / pyfortran10 / forterp.

They pin that the commands run a file, route program output to stdout, and that the
dialect boundary is visible at the CLI (pyf66 rejects a DEC feature pyfortran10 runs)."""

import io
import os
import tempfile

from forterp.cli import f66_main, f10_main, main

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


def test_check_reports_ok_on_clean_source(capsys):
    p = _src(HELLO_F66)  # strict-F66-clean (Hollerith FORMAT)
    try:
        rc = f66_main(["--check", p])
    finally:
        os.unlink(p)
    assert rc == 0
    assert "unit(s) OK" in capsys.readouterr().out
