"""Line-printer (LPT) device model -- FORTRAN-10 V5 Table 10-1.

A unit written to but never explicitly OPENed routes to its default device; units 3
and 6 default to the line printer. The interpreter models the printer as an injected
driver service (eng.printer); the test harness captures it to a buffer so printer
output can be verified separately from the terminal stream. This serves general
FORTRAN-10 source, e.g. the FCVS conformance listings, which write to unit 6.
"""

from conftest import out, printed, run

PROG = (
    "        PROGRAM T\n        COMMON /OUT/ V(40)\n"
    "        WRITE(6,10) 42\n"
    "  10    FORMAT(' ANS=',I3)\n"
)
END = "        END\n"


def test_unconnected_unit6_routes_to_printer():
    # leading ' ' is FORTRAN carriage control (single advance) -> consumed; the
    # record is terminated by its trailing newline.
    eng = run(PROG + END)
    assert printed(eng) == "ANS= 42\n"
    # and it did NOT leak into the terminal capture buffer
    assert "ANS" not in "".join(eng.out)


def test_unit3_also_defaults_to_lpt():
    eng = run("        PROGRAM T\n        WRITE(3,10)\n  10    FORMAT(' HELLO')\n" + END)
    assert printed(eng) == "HELLO\n"


def test_explicit_tty_open_overrides_default_device():
    # OPEN(6, DEVICE='TTY') makes unit 6 the terminal -> printer stays empty.
    eng = run(
        "        PROGRAM T\n        OPEN(UNIT=6,DEVICE='TTY',ACCESS='SEQOUT')\n"
        "        WRITE(6,10)\n  10    FORMAT(' TERM')\n" + END
    )
    assert printed(eng) == ""
    assert "TERM\n" in "".join(eng.out)


# ---- the READ side: unit 5 defaults to terminal input (V5 Table 10-1) ----
def test_unopened_unit5_reads_from_terminal_list_directed():
    # The documented READ(5,*) on an UNOPENED unit auto-connects to terminal input
    # (the injected readline) -- previously this silently no-op'd.
    src = (
        "        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n        COMMON /OUT/ V(40)\n"
        "        READ(5,*) A, B, C\n        V(1)=A\n        V(2)=B\n        V(3)=C\n" + END
    )
    eng = run(src, inputs=["10 20 30"])
    assert (out(eng, 1), out(eng, 2), out(eng, 3)) == (10, 20, 30)


def test_unopened_unit5_formatted_read():
    src = (
        "        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n        COMMON /OUT/ V(40)\n"
        "        READ(5,7) A, B\n    7 FORMAT(2I3)\n        V(1)=A\n        V(2)=B\n" + END
    )
    eng = run(src, inputs=["  5 42"])
    assert (out(eng, 1), out(eng, 2)) == (5, 42)
