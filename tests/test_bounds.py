"""Array bounds: the faithful unchecked default, and the opt-in declared-bounds check.

§5.4 requires a subscript to be within its declared bounds, but explicitly lets a processor
NOT detect a violation. forterp's default honors the FORTRAN-10 unchecked-storage model: an
out-of-bounds access traverses the COMMON / EQUIVALENCE storage sequence (the deliberate
over-/under-indexing tricks land in the neighbor), returning 0 only past the whole store. The
`bounds_check` dialect knob (engine `bounds_check=True`) opts in to the gfortran -fcheck=bounds
behavior: any subscript outside its declared [lo,hi] raises OobError, even when it would land in
a valid neighbor.
"""

import dataclasses

import pytest

import forterp

# ---- faithful default: the vintage over-/under-indexing tricks work --------------------------


def test_oob_read_reaches_the_next_common_variable():
    # A(3),B laid contiguously: A(4) is B. The unchecked model returns B's value, not 0.
    src = (
        "      PROGRAM T\n      COMMON /O/ N(2)\n      COMMON /X/ A(3),B\n"
        "      B=42.0\n      N(1)=A(4)\n      END\n"
    )
    eng = forterp.run_source(src, dialect=forterp.FORTRAN10, target=forterp.PDP10)
    assert eng.commons["O"][0] == 42


def test_oob_write_through_to_the_neighbor():
    src = (
        "      PROGRAM T\n      COMMON /O/ N(2)\n      COMMON /X/ A(3),B\n"
        "      A(4)=99.0\n      N(1)=B\n      END\n"
    )
    eng = forterp.run_source(src, dialect=forterp.FORTRAN10, target=forterp.PDP10)
    assert eng.commons["O"][0] == 99


def test_far_oob_past_the_whole_store_reads_zero():
    src = (
        "      PROGRAM T\n      COMMON /O/ N(2)\n      COMMON /X/ A(3)\n"
        "      N(1)=A(1000)\n      END\n"
    )
    eng = forterp.run_source(src, dialect=forterp.FORTRAN10, target=forterp.PDP10)
    assert eng.commons["O"][0] == 0


# ---- opt-in declared-bounds check (bounds_check) ---------------------------------------------

_CHECK = dataclasses.replace(forterp.FORTRAN10, bounds_check=True)


def test_bounds_check_traps_an_out_of_bounds_subscript():
    src = (
        "      PROGRAM T\n      COMMON /O/ N(2)\n      COMMON /X/ A(3),B\n"
        "      B=42.0\n      N(1)=A(4)\n      END\n"
    )
    # Without the gate this faithfully reads B; with it, A(4) is outside [1:3] -> a hard error,
    # even though it lands in valid neighboring storage.
    with pytest.raises(forterp.engine.OobError) as exc:
        forterp.run_source(src, dialect=_CHECK, target=forterp.PDP10)
    assert "outside its declared bounds" in str(exc.value)


def test_bounds_check_allows_in_bounds_access():
    src = (
        "      PROGRAM T\n      COMMON /O/ N(2)\n      DIMENSION A(3)\n"
        "      A(2)=7.0\n      N(1)=A(2)\n      END\n"
    )
    eng = forterp.run_source(src, dialect=_CHECK, target=forterp.NATIVE)
    assert eng.commons["O"][0] == 7


def test_bounds_check_traps_below_the_lower_bound():
    # Lower-bound violation too: A declared (2:4); A(1) is below 2.
    src = (
        "      PROGRAM T\n      COMMON /O/ N(2)\n      DIMENSION A(2:4)\n"
        "      N(1)=A(1)\n      END\n"
    )
    with pytest.raises(forterp.engine.OobError):
        forterp.run_source(src, dialect=_CHECK, target=forterp.NATIVE)


# ---- §5.7.1 substring bounds: 1 <= e1 <= e2 <= len -------------------------------------------

_CSTR = forterp.F77
_CSTR_CHECK = dataclasses.replace(forterp.F77, bounds_check=True)


def _csub(body, dialect):
    src = (
        "      PROGRAM T\n      COMMON /O/ C\n      CHARACTER*4 S\n      CHARACTER*9 C\n"
        + body
        + "      END\n"
    )
    return forterp.run_source(src, dialect=dialect, target=forterp.NATIVE).commons["O"]


def test_out_of_range_substring_is_lenient_by_default():
    # Default: S(1:9) of a CHARACTER*4 clamps to the 4 available characters (later padded to 9).
    assert _csub("      S='ABCD'\n      C=S(1:9)\n", _CSTR)[0] == "ABCD     "


@pytest.mark.parametrize("expr", ["S(1:9)", "S(0:2)", "S(3:1)"])
def test_bounds_check_traps_out_of_range_substring_read(expr):
    # §5.7.1: e2>len, e1<1, and e1>e2 are all violations -- a hard error under the gate.
    with pytest.raises(forterp.engine.OobError):
        _csub(f"      S='ABCD'\n      C={expr}\n", _CSTR_CHECK)


def test_bounds_check_traps_out_of_range_substring_assignment():
    with pytest.raises(forterp.engine.OobError):
        _csub("      S='ABCD'\n      S(2:9)='XY'\n      C=S\n", _CSTR_CHECK)


def test_in_range_substring_is_fine_under_the_gate():
    assert _csub("      S='ABCD'\n      C=S(2:3)\n", _CSTR_CHECK)[0] == "BC       "
