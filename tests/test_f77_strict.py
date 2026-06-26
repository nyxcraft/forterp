"""ANSI X3.9-1978 strict enforcement -- the cases where the F77 dialect REJECTS a nonconforming
program that the lenient real-compiler dialects (F66, FORTRAN-10) accept silently.

The standard places these as requirements on a conforming *program* (§1.4 lets a processor
detect them or not); forterp's F77 dialect is the one meant to model the standard, so it
diagnoses them, while FORTRAN-10 stays faithful to what the real DEC compiler accepted. Each
strict check is gated by a `Dialect` knob (default off) and verified FCVS-clean before shipping.
"""

import pytest

import forterp

# A program unit with a specification statement (DIMENSION) placed AFTER an executable
# statement -- a violation of F77 §3.5 ("all specification statements must precede ... all
# executable statements").
_OUT_OF_ORDER = (
    "      PROGRAM T\n"
    "      COMMON /O/ N(4)\n"
    "      N(1) = 1\n"  # executable
    "      DIMENSION A(3)\n"  # specification statement -- too late
    "      N(2) = 2\n"
    "      END\n"
)


def test_f77_rejects_a_specification_statement_after_an_executable():
    # §3.5: hard error under the strict F77 dialect.
    with pytest.raises(forterp.ParseError) as exc:
        forterp.run_source(_OUT_OF_ORDER, dialect=forterp.F77, target=forterp.NATIVE)
    assert "OUT OF ORDER" in str(exc.value)


def test_fortran10_accepts_the_same_out_of_order_program():
    # FORTRAN-10 is lenient (faithful to the real DEC compiler) -- it parses and runs.
    eng = forterp.run_source(_OUT_OF_ORDER, dialect=forterp.FORTRAN10, target=forterp.NATIVE)
    assert eng.commons["O"][:2] == [1, 2]


def test_f66_also_accepts_the_out_of_order_program():
    # F66 (the other lenient real-compiler dialect) accepts it too. (DIMENSION is F66; the
    # snippet uses no F77-only feature, so it is valid F66 source.)
    eng = forterp.run_source(_OUT_OF_ORDER, dialect=forterp.F66, target=forterp.NATIVE)
    assert eng.commons["O"][:2] == [1, 2]


def test_f77_accepts_a_correctly_ordered_program():
    # The same statements in the conforming order parse and run fine under F77.
    src = (
        "      PROGRAM T\n"
        "      COMMON /O/ N(4)\n"
        "      DIMENSION A(3)\n"  # specification statements first
        "      N(1) = 1\n"  # then executables
        "      N(2) = 2\n"
        "      END\n"
    )
    eng = forterp.run_source(src, dialect=forterp.F77, target=forterp.NATIVE)
    assert eng.commons["O"][:2] == [1, 2]


def test_f77_allows_data_after_an_executable():
    # §3.5(4): DATA statements "may appear anywhere after the specification statements" --
    # including among the executables. DATA is NOT a specification statement for ordering, so
    # the strict check must not flag it.
    src = (
        "      PROGRAM T\n"
        "      COMMON /O/ N(4)\n"
        "      N(1) = 7\n"  # executable
        "      DATA K /5/\n"  # DATA after an executable -- legal
        "      N(2) = K\n"
        "      END\n"
    )
    eng = forterp.run_source(src, dialect=forterp.F77, target=forterp.NATIVE)
    assert eng.commons["O"][:2] == [7, 5]


def test_f77_allows_format_after_an_executable():
    # §3.5(1): FORMAT statements "may appear anywhere". A FORMAT after an executable is legal.
    src = (
        "      PROGRAM T\n"
        "      COMMON /O/ C\n"
        "      CHARACTER*8 C\n"
        "      WRITE(C,10) 42\n"  # executable
        "10    FORMAT(I8)\n"  # FORMAT after it -- legal
        "      END\n"
    )
    eng = forterp.run_source(src, dialect=forterp.F77, target=forterp.NATIVE)
    assert eng.commons["O"] == ["      42"]


def test_save_as_a_variable_name_after_an_executable_is_not_flagged():
    # `SAVE = ...` is an assignment to a variable named SAVE, not the SAVE statement, so the
    # order check must leave it alone even after an executable. (SAVE is a no-op statement here,
    # but the assignment form must still parse.)
    src = (
        "      PROGRAM T\n"
        "      COMMON /O/ N(2)\n"
        "      N(1) = 1\n"
        "      SAVE = 9\n"  # assignment, not the SAVE specification statement
        "      N(2) = SAVE\n"
        "      END\n"
    )
    eng = forterp.run_source(src, dialect=forterp.F77, target=forterp.NATIVE)
    assert eng.commons["O"][:2] == [1, 9]
