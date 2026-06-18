"""Dialect boundary: what the Empire FORTRAN-10 dialect accepts vs what it doesn't.

The interpreter targets DEC FORTRAN-10 as Empire uses it (F66-era + DEC extensions),
NOT FORTRAN-77. These tests pin both the supported forms and the F77 constructs that
correctly do NOT parse -- a regression here would mean we drifted toward F77.
"""

from conftest import run, run_int, out

H = "        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n        COMMON /OUT/ V(40)\n"
END = "        END\n"


def _rejected(src):
    """True if the snippet fails to parse (raises from the harness)."""
    try:
        run(src)
        return False
    except Exception:
        return True


# ---- supported DEC FORTRAN-10 forms (the game relies on these) ----
def test_caret_is_the_power_operator():
    assert out(run_int("        V(1)=2^10\n"), 1) == 1024


def test_parenless_parameter_is_accepted():
    # DEC/F66 style used by the game: PARAMETER X=val (no parentheses)
    src = ("        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n        PARAMETER K=5\n"
           "        COMMON /OUT/ V(40)\n        V(1)=K*2\n" + END)
    assert out(run(src), 1) == 10


def test_parenthesized_parameter_also_accepted():
    src = ("        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n        PARAMETER (K=5)\n"
           "        COMMON /OUT/ V(40)\n        V(1)=K*2\n" + END)
    assert out(run(src), 1) == 10


def test_octal_and_symbolic_relationals_are_dialect_features():
    eng = run_int('        V(1)="20\n        V(2)=0\n        IF(2#3) V(2)=1\n')
    assert out(eng, 1) == 16
    assert out(eng, 2) == 1


# ---- F77-only constructs: correctly NOT supported in this F66 dialect ----
def test_block_if_then_endif_is_rejected():
    assert _rejected(H + "        IF(1==1) THEN\n        V(1)=9\n        ENDIF\n" + END)


def test_do_while_is_rejected():
    assert _rejected(H + "        DO WHILE(V(1)<3)\n        V(1)=V(1)+1\n        END DO\n" + END)


# ---- ** (standard FORTRAN power) is accepted as a synonym for ^ ----
# The game uses '^' exclusively, but '**' is standard FORTRAN-66 power; the lexer
# now emits the same power token for both so general F66 code works too.
def test_double_star_is_power_synonym_for_caret():
    assert out(run_int("        V(1)=2**10\n"), 1) == 1024
    assert out(run_int("        V(1)=2**3*2\n"), 1) == 16     # binds tighter than *
    assert out(run_int("        V(1)=2^10\n"), 1) == 1024     # ^ still works
