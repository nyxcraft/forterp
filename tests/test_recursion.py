"""Recursion handling -- §15.5.2 ("A subprogram must not reference itself, either directly or
indirectly").

forterp stores a unit's locals statically on the routine (faithful to the FORTRAN-77 / FORTRAN-10
static-storage model, where SAVE is a no-op). That model cannot represent recursion: a nested
activation would clobber the caller's locals. Historically forterp ran such a program anyway and
returned a silently wrong answer. Now:

  * default (every dialect): re-entry of a still-active unit is detected and raises
    IllegalRecursion -- a clean error beats silent corruption, and the period compilers did not
    support recursion either.
  * opt-in per procedure (the F90 `RECURSIVE` keyword): that procedure may recurse even with the
    knob off -- the per-procedure opt-in, like gfortran's RECURSIVE / -frecursive.
  * opt-in globally (`recursion` dialect knob / `allow_recursion` engine flag): every procedure may
    recurse. Either way it is made correct by snapshotting and restoring the active unit's locals
    around the nested call.

The capability is dialect-independent -- it works with F66, FORTRAN10, and F77 alike.
"""

import dataclasses

import pytest

import forterp

DIALECTS = [forterp.F66, forterp.FORTRAN10, forterp.F77]

# F66-valid recursive factorial that uses a LOCAL (L) AFTER the recursive call -- the case the
# old static-storage path got wrong (it returned 8 for IFA(4) instead of 24).
_FACTORIAL = (
    "      PROGRAM T\n"
    "      COMMON /O/ N(2)\n"
    "      N(1)=IFA(4)\n"
    "      END\n"
    "      INTEGER FUNCTION IFA(K)\n"
    "      IF(K.LE.1) GO TO 10\n"
    "      L=K\n"
    "      M=IFA(K-1)\n"
    "      IFA=L*M\n"
    "      RETURN\n"
    "10    IFA=1\n"
    "      RETURN\n"
    "      END\n"
)


@pytest.mark.parametrize("dialect", DIALECTS, ids=lambda d: f"d{id(d) % 1000}")
def test_recursion_is_rejected_by_default_on_every_dialect(dialect):
    with pytest.raises(forterp.engine.IllegalRecursion):
        forterp.run_source(_FACTORIAL, dialect=dialect, target=forterp.NATIVE)


@pytest.mark.parametrize("dialect", DIALECTS, ids=lambda d: f"d{id(d) % 1000}")
def test_recursion_when_enabled_is_correct_on_every_dialect(dialect):
    # The gate must yield the CORRECT answer, not just "run": IFA(4)=4*3*2*1=24, which is only
    # right if the local L survives each nested call (Option B save/restore).
    rec = dataclasses.replace(dialect, recursion=True)
    eng = forterp.run_source(_FACTORIAL, dialect=rec, target=forterp.NATIVE)
    assert eng.commons["O"][0] == 24


def test_enabled_recursion_handles_branching_recursion():
    # Fibonacci exercises two recursive calls per frame; F(10)=55.
    src = (
        "      PROGRAM T\n"
        "      COMMON /O/ N(2)\n"
        "      N(1)=IFIB(10)\n"
        "      END\n"
        "      INTEGER FUNCTION IFIB(K)\n"
        "      IF(K.GE.2) GO TO 10\n"
        "      IFIB=K\n"
        "      RETURN\n"
        "10    IFIB=IFIB(K-1)+IFIB(K-2)\n"
        "      RETURN\n"
        "      END\n"
    )
    rec = dataclasses.replace(forterp.F77, recursion=True)
    assert forterp.run_source(src, dialect=rec, target=forterp.NATIVE).commons["O"][0] == 55


def test_enabled_recursion_keeps_common_shared_across_activations():
    # COMMON is NOT local -- it must stay shared across recursive activations (only locals are
    # snapshotted). Each activation increments a COMMON counter; after IDEC(3) it reads 3.
    src = (
        "      PROGRAM T\n"
        "      COMMON /O/ N(2)\n"
        "      COMMON /CTR/ IC\n"
        "      IC=0\n"
        "      J=IDEC(3)\n"
        "      N(1)=IC\n"
        "      END\n"
        "      INTEGER FUNCTION IDEC(K)\n"
        "      COMMON /CTR/ IC\n"
        "      IC=IC+1\n"
        "      IF(K.LE.1) GO TO 10\n"
        "      J=IDEC(K-1)\n"
        "10    IDEC=0\n"
        "      RETURN\n"
        "      END\n"
    )
    rec = dataclasses.replace(forterp.F77, recursion=True)
    assert forterp.run_source(src, dialect=rec, target=forterp.NATIVE).commons["O"][0] == 3


def test_indirect_recursion_is_detected():
    # §15.5.2 covers indirect self-reference: A calls B calls A. Rejected by default.
    src = (
        "      PROGRAM T\n"
        "      COMMON /O/ N(2)\n"
        "      N(1)=IA(3)\n"
        "      END\n"
        "      INTEGER FUNCTION IA(K)\n"
        "      IA=IB(K)\n"
        "      RETURN\n"
        "      END\n"
        "      INTEGER FUNCTION IB(K)\n"
        "      IB=IA(K-1)\n"
        "      RETURN\n"
        "      END\n"
    )
    with pytest.raises(forterp.engine.IllegalRecursion):
        forterp.run_source(src, dialect=forterp.F77, target=forterp.NATIVE)


def test_subroutine_recursion_is_rejected():
    # The guard covers CALL of a subroutine too, not just function references.
    src = (
        "      PROGRAM T\n"
        "      COMMON /O/ N(2)\n"
        "      CALL SUB(3)\n"
        "      END\n"
        "      SUBROUTINE SUB(K)\n"
        "      IF(K.LE.0) RETURN\n"
        "      CALL SUB(K-1)\n"
        "      RETURN\n"
        "      END\n"
    )
    with pytest.raises(forterp.engine.IllegalRecursion):
        forterp.run_source(src, dialect=forterp.F77, target=forterp.NATIVE)


def test_non_recursive_repeated_calls_still_work():
    # The guard must not trip on ordinary repeated (non-nested) calls to the same unit.
    src = (
        "      PROGRAM T\n"
        "      COMMON /O/ N(3)\n"
        "      N(1)=ISQ(2)\n"
        "      N(2)=ISQ(5)\n"
        "      N(3)=ISQ(7)\n"
        "      END\n"
        "      INTEGER FUNCTION ISQ(K)\n"
        "      ISQ=K*K\n"
        "      RETURN\n"
        "      END\n"
    )
    eng = forterp.run_source(src, dialect=forterp.F77, target=forterp.NATIVE)
    assert eng.commons["O"][:3] == [4, 25, 49]


# ---- the RECURSIVE keyword (F90): per-procedure opt-in, like gfortran ----
# A procedure declared RECURSIVE may reference itself even with the `recursion` knob OFF (the
# default); it gets correct per-activation local storage. This mirrors gfortran, where a self-
# referencing procedure needs the RECURSIVE keyword (or -frecursive) and is otherwise rejected.

_REC_FAC = (
    "      {header}\n"
    "      IF (N.LE.1) THEN\n      IFAC=1\n      ELSE\n      IFAC=N*IFAC(N-1)\n      END IF\n"
    "      RETURN\n      END\n"
    "      PROGRAM T\n      COMMON /O/ R\n      INTEGER R\n      R=IFAC(5)\n      END\n"
)


@pytest.mark.parametrize(
    "header",
    [
        "RECURSIVE INTEGER FUNCTION IFAC(N)",
        "INTEGER RECURSIVE FUNCTION IFAC(N)",  # the other F90 keyword order
        "RECURSIVE FUNCTION IFAC(N)",  # implicit (integer) result type
    ],
)
def test_recursive_keyword_enables_recursion_with_knob_off(header):
    src = _REC_FAC.format(header=header)
    eng = forterp.run_source(src, dialect=forterp.FORTRAN10, target=forterp.NATIVE)
    assert eng.commons["O"][0] == 120  # 5! -- correct per-activation storage, no knob needed


def test_plain_function_still_rejected_without_recursive_or_knob():
    src = _REC_FAC.format(header="INTEGER FUNCTION IFAC(N)")
    with pytest.raises(forterp.engine.IllegalRecursion):
        forterp.run_source(src, dialect=forterp.FORTRAN10, target=forterp.NATIVE)


def test_recursive_subroutine():
    src = (
        "      RECURSIVE SUBROUTINE COUNT(N)\n      COMMON /O/ R\n      INTEGER R\n"
        "      IF (N.GT.0) THEN\n      R=R+1\n      CALL COUNT(N-1)\n      END IF\n"
        "      RETURN\n      END\n"
        "      PROGRAM T\n      COMMON /O/ R\n      INTEGER R\n"
        "      R=0\n      CALL COUNT(5)\n      END\n"
    )
    eng = forterp.run_source(src, dialect=forterp.FORTRAN10, target=forterp.NATIVE)
    assert eng.commons["O"][0] == 5


def test_recursive_local_equivalence_is_isolated_per_activation():
    """A unit's local EQUIVALENCE storage lives in synthetic $EQV blocks; a recursive activation
    must get its own, not share the caller's (external review #2). F(2): the outer A=2 must
    survive the nested F(1), so F returns 2 -- not 1, as it did when $EQV was not snapshotted."""
    src = """      PROGRAM T
      COMMON /O/ R
      R = F(2)
      END
      RECURSIVE FUNCTION F(N)
      EQUIVALENCE (A, B)
      A = N
      IF (N .GT. 1) X = F(N-1)
      F = B
      RETURN
      END
"""
    eng = forterp.run_source(src, dialect=forterp.FORTRAN10, target=forterp.NATIVE)
    assert eng.commons["O"][0] == 2
