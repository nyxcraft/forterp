"""The standard TOPS-10 monitor UUOs (forterp.uuolib): installed under the FORTRAN-10 dialect,
absent from strict F66, and overridable by a host that registers its own."""

import forterp
from forterp.uuolib import UUOLIB

TRIVIAL = "      PROGRAM T\n      END\n"


def test_installed_under_fortran10():
    eng = forterp.fortran10.run_source(TRIVIAL, emit=lambda s: None)
    assert all(name in eng.builtins for name in UUOLIB)


def test_absent_under_strict_f66():
    eng = forterp.f66.run_source(TRIVIAL, emit=lambda s: None)
    assert not any(name in eng.builtins for name in UUOLIB)


def test_outstr_and_outchr_write_to_the_terminal():
    out = []
    forterp.fortran10.run_source(
        "      PROGRAM T\n      CALL OUTSTR('HI')\n      CALL OUTCHR(65)\n      END\n",
        emit=out.append,
    )
    assert "".join(out) == "HIA"  # OUTSTR text, then OUTCHR 65 -> 'A'


def test_a_program_defined_routine_still_wins():
    # the program's own OUTSTR shadows the library one (never shadow a defined unit)
    src = (
        "      PROGRAM T\n      CALL OUTSTR(0)\n      END\n"
        "      SUBROUTINE OUTSTR(X)\n      CALL OUTCHR(90)\n      RETURN\n      END\n"
    )
    out = []
    forterp.fortran10.run_source(src, emit=out.append)
    assert "".join(out) == "Z"  # the program's OUTSTR ran (emits 'Z'), not the library one
