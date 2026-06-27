"""Smoke tests for the console entry points (forterp.cli): pyf66 / pyfortran10 / forterp.

They pin that the commands run a file, route program output to stdout, and that the
dialect boundary is visible at the CLI (pyf66 rejects a DEC feature pyfortran10 runs)."""

import io
import os
import tempfile

import pytest

from forterp.cli import f10_main, f66_main, f77_main, main

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


def test_pyf77_runs_character_feature(capsys):
    # CHARACTER is an F77 type (rejected under strict F66) -- pyf77 must accept and run it.
    f77 = (
        "      PROGRAM T\n      CHARACTER*9 S\n"
        "      S = 'HELLO F77'\n      WRITE(6,*) S\n      END\n"
    )
    p = _src(f77)
    try:
        rc = f77_main([p])
    finally:
        os.unlink(p)
    assert rc == 0
    assert "HELLO F77" in capsys.readouterr().out


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
    "from forterp.hostlib import fcall, INT\n\n\n"
    "@fcall('IDIST', args=(INT, INT))\n"
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


def test_load_builtins_restores_sys_path_and_modules():
    # loading a host .py must not leak into the global import state (a file named like a stdlib
    # module would otherwise shadow later imports in an in-process embedder / the test suite).
    import sys

    from forterp.cli import _load_builtins

    d = tempfile.mkdtemp()
    modname = "forterp_probe_hostmod"
    path = os.path.join(d, modname + ".py")
    with open(path, "w") as f:
        f.write(_PY_BUILTIN)
    path_before = list(sys.path)
    assert modname not in sys.modules
    dont_write_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True  # no __pycache__, so cleanup is exactly the file + dir we made
    try:
        table, _hooks = _load_builtins([path])
    finally:
        sys.dont_write_bytecode = dont_write_bytecode
        os.unlink(path)
        os.rmdir(d)
    assert "IDIST" in table  # the routine was still discovered during loading
    assert modname not in sys.modules  # ... but the module name is not left behind
    assert sys.path == path_before  # ... and the inserted directory was removed


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


def test_version_flag_long_and_short(capsys):
    # --version and -V both print "<prog> <version>" and exit 0, Python-style.
    import forterp

    for flag in ("--version", "-V"):
        assert f10_main([flag]) == 0
        assert capsys.readouterr().out.strip() == f"pyfortran10 {forterp.__version__}"
    # -VV adds the dialect/target/host build line
    assert f10_main(["-VV"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("pyfortran10 ") and "target)" in out and "on " in out


_END = "\n      END\n"


def test_dash_c_runs_a_program_string(capsys):
    # -c CMD runs the FORTRAN program passed as a string (cf. python -c).
    assert f10_main(["-c", "      PRINT *, 2+2" + _END]) == 0
    assert "4" in capsys.readouterr().out


def test_dash_reads_program_from_stdin(monkeypatch, capsys):
    # a "-" file argument reads the program from stdin.
    monkeypatch.setattr("sys.stdin", io.StringIO("      PROGRAM T\n      PRINT *, 6*7" + _END))
    assert f10_main(["-"]) == 0
    assert "42" in capsys.readouterr().out


def test_dash_x_skips_the_first_line(capsys):
    # -x skips the source's first line, so a #! shebang line doesn't reach the parser.
    p = _src("#!/usr/bin/env forterp\n" + HELLO_F66)
    try:
        assert f66_main(["-x", p]) == 0  # runs cleanly with -x
        assert "HELLO FROM F66" in capsys.readouterr().out
        assert f66_main([p]) == 1  # without -x the '#!' line is a parse error
    finally:
        os.unlink(p)


def test_quiet_suppresses_the_banner(monkeypatch, capsys):
    # -q drops the interactive startup banner; the prompt still appears.
    monkeypatch.setattr("sys.stdin", io.StringIO("EXIT\n"))
    assert f66_main(["-q"]) == 0
    out = capsys.readouterr().out
    assert "Type HELP" not in out  # banner suppressed
    assert "f66>" in out  # prompt still shown


def test_unbuffered_flag_runs(capsys):
    # -u reconfigures the streams unbuffered; the program still runs and prints.
    assert f10_main(["-u", "-c", "      PRINT *, 1+1" + _END]) == 0
    assert "2" in capsys.readouterr().out


def test_inspect_after_run_enters_the_processor(monkeypatch, capsys):
    # -i runs the program, then drops into the command processor with the engine available,
    # so SHOW /BLOCK/ can inspect what the run left in COMMON.
    monkeypatch.setattr("sys.stdin", io.StringIO("SHOW /OUT/\nEXIT\n"))
    prog = "      COMMON /OUT/ N\n      N = 99" + _END
    assert f10_main(["-i", "-q", "-c", prog]) == 0
    assert "99" in capsys.readouterr().out  # SHOW /OUT/ reported the post-run value


def test_mount_device_serves_open(capsys):
    """--mount DEV=DIR registers an OPEN device that serves files from DIR: a program that
    OPEN(DEVICE='DEV', FILE='F')s reads DIR/F through the ordinary sequential machinery."""
    import os
    import tempfile

    mnt = tempfile.mkdtemp()
    with open(os.path.join(mnt, "DATA.TXT"), "w") as fh:
        fh.write("  123\n  456\n")
    src = _src(
        "      PROGRAM R\n"
        "      OPEN(UNIT=1,DEVICE='GAM',FILE='DATA.TXT',ACCESS='SEQIN')\n"
        "      READ(1,10) N\n"
        "      READ(1,10) M\n"
        "   10 FORMAT(I5)\n"
        "      TYPE 20, N, M\n"
        "   20 FORMAT(' GOT ',I5,I5)\n"
        "      END\n"
    )
    try:
        rc = f10_main(["--mount", f"GAM={mnt}", src])
    finally:
        os.unlink(src)
    assert rc == 0
    assert "GOT   123  456" in capsys.readouterr().out


def test_mount_bad_spec_is_arg_error():
    """--mount without '=' is a clean argparse error, not a traceback."""
    with pytest.raises(SystemExit):
        f10_main(["--mount", "NODELIM", "-c", "      END\n"])
