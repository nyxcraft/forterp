"""Interactive command processor (forterp.command.CommandProcessor): RUN/CHECK/LOAD/START/SET/SHOW.

Drives the command processor with a scripted line source and captures its output, pinning the
command set the pyf66 / pyfortran10 / forterp front-ends expose when launched with no
file. The set is identical across the three; only the starting dialect differs."""

import io
import os
import tempfile

from forterp.cli import f66_main
from forterp.command import CommandProcessor

# strict-F66-clean: Hollerith FORMAT (the command processor defaults to f66, which rejects '...')
HELLO = "      PROGRAM T\n      WRITE(6,10)\n   10 FORMAT(7H HI MON)\n      END\n"
# writes COMMON so SHOW /OUT/ has state to print after a run
COMMON_PROG = (
    "      PROGRAM T\n      COMMON /OUT/ V(3)\n      INTEGER V\n"
    "      V(1)=11\n      V(2)=22\n      V(3)=33\n      END\n"
)
# IMPLICIT is a FORTRAN-10 statement -- rejected under strict f66
DEC = (
    "      PROGRAM T\n      IMPLICIT INTEGER(A-Z)\n"
    "      WRITE(6,10)\n   10 FORMAT(' DEC OK')\n      END\n"
)


def _src(text):
    with tempfile.NamedTemporaryFile("w", suffix=".FOR", delete=False) as f:
        f.write(text)
        return f.name


def drive(lines, **kw):
    """Run the command processor over a scripted command list; return (stdout, stderr)."""
    it = iter(lines)
    out, err = [], []
    CommandProcessor(
        write=out.append, errwrite=err.append, readline=lambda: next(it, ""), **kw
    ).run()
    return "".join(out), "".join(err)


def test_run_executes_a_file():
    p = _src(HELLO)
    try:
        out, _ = drive([f"RUN {p}\n", "EXIT\n"])
    finally:
        os.unlink(p)
    assert "HI MON" in out


def test_execute_is_an_alias_for_run():
    p = _src(HELLO)
    try:
        out, _ = drive([f"EXECUTE {p}\n"])  # EOF then ends the loop
    finally:
        os.unlink(p)
    assert "HI MON" in out


def test_check_reports_ok_and_does_not_run():
    p = _src(HELLO)
    try:
        out, _ = drive([f"CHECK {p}\n"])
    finally:
        os.unlink(p)
    assert "unit(s) OK" in out
    assert "HI MON" not in out  # CHECK parses but does not run


def test_check_lists_diagnostics_under_f66():
    p = _src(DEC)
    try:
        _, err = drive([f"CHECK {p}\n"], std="f66")
    finally:
        os.unlink(p)
    assert "error(s)" in err and "IMPLICIT" in err


def test_set_std_switches_dialect():
    p = _src(DEC)
    try:
        # rejected under f66; after SET STD fortran10 the same source runs
        out, err = drive([f"RUN {p}\n", "SET STD fortran10\n", f"RUN {p}\n"], std="f66")
    finally:
        os.unlink(p)
    assert "IMPLICIT" in err  # first run rejected
    assert "DEC OK" in out  # second run succeeded


def test_load_then_start():
    p = _src(HELLO)
    try:
        out, _ = drive([f"LOAD {p}\n", "START\n"])
    finally:
        os.unlink(p)
    assert "loaded" in out and "HI MON" in out


def test_start_without_load_errors():
    _, err = drive(["START\n"])
    assert "nothing loaded" in err.lower()


def test_show_settings_reflects_initial_state():
    out, _ = drive(["SHOW\n"], std="fortran10", target="pdp10")
    assert "fortran10" in out and "pdp10" in out


def test_show_common_block_after_run():
    p = _src(COMMON_PROG)
    try:
        out, _ = drive([f"RUN {p}\n", "SHOW /OUT/\n"])
    finally:
        os.unlink(p)
    assert "/OUT/" in out and "11" in out and "33" in out


def test_unknown_command_is_reported():
    _, err = drive(["FROBNICATE\n"])
    assert "Unknown command" in err


def test_help_lists_the_core_commands():
    out, _ = drive(["HELP\n"])
    for c in ("RUN", "CHECK", "LOAD", "START", "SET", "SHOW", "EXIT"):
        assert c in out


def test_info_commands_copyright_credits_license():
    out, _ = drive(["COPYRIGHT\n", "CREDITS\n", "LICENSE\n", "EXIT\n"])
    assert "Copyright (c) 2026 Nicholas J. Kisseberth" in out  # COPYRIGHT
    assert "Anthropic Claude Code" in out  # CREDITS
    assert "MIT License" in out and "WITHOUT WARRANTY" in out  # LICENSE full text


def test_immediate_command_enters_the_repl():
    # IMMEDIATE drops into the REPL (reading the same input); first EXIT returns to the
    # command processor, second EXIT quits. The expression's value reaches stdout.
    out, _ = drive(["IMMEDIATE\n", "2 + 3\n", "EXIT\n", "EXIT\n"])
    assert "immediate mode" in out and "5" in out


def test_bare_invocation_enters_the_command_processor(monkeypatch, capsys):
    # pyf66 with no file -> interactive command processor reading from stdin
    monkeypatch.setattr("sys.stdin", io.StringIO("HELP\nEXIT\n"))
    rc = f66_main([])
    out = capsys.readouterr().out
    assert rc == 0
    assert "RUN" in out  # HELP listed the commands
    assert out.startswith("forterp ") and "FORTRAN-66" in out  # the interpreter-style banner
    assert "Type HELP for commands" in out


def test_ctrl_c_at_the_prompt_reprompts_and_does_not_crash():
    # ^C while waiting for input must abandon the line and re-prompt, not escape out of run().
    seq = iter([KeyboardInterrupt, "EXIT\n"])

    def readline():
        item = next(seq, "")
        if item is KeyboardInterrupt:
            raise KeyboardInterrupt
        return item

    out, err = [], []
    rc = CommandProcessor(write=out.append, errwrite=err.append, readline=readline).run()
    assert rc == 0  # exited cleanly on EXIT after the ^C, no traceback
    assert "".join(out).count("f66>") >= 2  # re-prompted after the interrupt
