"""FORTRAN-10 terminal 'free CR-LF': emit() wraps terminal output at the carriage width (the
TOPS-10 monitor's line discipline). DEC dialect only -- strict F66 never wraps. A program turns
it off via TRMOP2 (.TONFC) for a cursor-addressed full-screen display. Line-printer output is not
subject to the terminal margin."""

import forterp


def _f10_out(body):
    """Run a FORTRAN-10 program (body is the statements between PROGRAM and END) and return the
    terminal output. Uses OUTCHR loops so the source lines stay within column 72."""
    out = []
    forterp.fortran10.run_source("      PROGRAM T\n" + body + "      END\n", emit=out.append)
    return "".join(out)


def test_wraps_at_eighty_under_fortran10():
    # 85 chars to the terminal -> 80 on the first line, a free CR-LF, then 5
    out = _f10_out("      DO 10 I=1,85\n      CALL OUTCHR(65)\n10    CONTINUE\n")
    assert out == "A" * 80 + "\n" + "A" * 5


def test_deferred_wrap_exactly_eighty_does_not_break_early():
    # exactly 80 fit; the 81st printing char triggers the wrap (deferred, like the monitor)
    prog = "      DO 10 I=1,80\n      CALL OUTCHR(65)\n10    CONTINUE\n      CALL OUTCHR(66)\n"
    assert _f10_out(prog) == "A" * 80 + "\nB"


def test_autowrap_off_disables_the_wrap():
    # a program disabling free-CR-LF (Empire's TRMOP2 / .TONFC) drives eng.set_autowrap(False);
    # the long line is then NOT wrapped. (TRMOP2 itself is a sixbit host routine, not a forterp
    # builtin, so the engine mechanism it calls is what's exercised here.)
    out = []
    eng = forterp.fortran10.build_engine({}, emit=out.append)
    eng.set_autowrap(False)
    eng.emit("X" * 85)
    assert "".join(out) == "X" * 85
    assert "\n" not in "".join(out)


def test_strict_f66_never_wraps():
    # the wrap is a DEC/TOPS-10 behavior (gated on dec_intrinsics); strict F66 emits verbatim
    out = []
    eng = forterp.f66.build_engine({}, emit=out.append)
    eng.emit("X" * 85)
    assert "".join(out) == "X" * 85


def test_engine_default_width_is_eighty():
    out = []
    eng = forterp.fortran10.build_engine({}, emit=out.append)
    assert eng._tty_width == 80
    eng.emit("X" * 85)
    assert "".join(out) == "X" * 80 + "\n" + "X" * 5


def test_width_zero_disables_wrap():
    out = []
    eng = forterp.fortran10.build_engine({}, emit=out.append, tty_width=0)
    eng.emit("X" * 85)
    assert "".join(out) == "X" * 85


def test_line_printer_output_is_not_margin_wrapped():
    # unit 6 -> the line printer, which has its own width; the terminal free-CR-LF must not apply
    out = []
    forterp.fortran10.run_source(
        "      PROGRAM T\n      WRITE(6,1)\n1     FORMAT(1X,90('X'))\n      END\n",
        emit=out.append,
    )
    assert "X" * 81 in "".join(out)  # 81+ consecutive X's => no wrap was inserted at column 80
