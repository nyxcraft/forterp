"""Tier-3 front-end fidelity (V5 §3.3 / §15.3 / terminal input):
6-character identifier truncation, EXTERNAL with the */& intrinsic-override
prefix, and CONTROL-Z = end-of-file on terminal input. The Empire test case uses
none of these (its names are all <=6 chars, no EXTERNAL), so they are general
FORTRAN-10 V5 coverage verified not to disturb the game (parsecheck/fuzz clean).
"""

from conftest import run, run_int, out

IH = ("        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n"
      "        COMMON /OUT/ V(40)\n")
END = "        END\n"


# ---- 6-char identifier truncation (V5 3.3) ---------------------------------
def test_identifier_truncated_to_six_chars():
    # COUNTER and COUNTED both truncate to COUNTE -> the SAME variable
    eng = run_int("        COUNTER=7\n        V(1)=COUNTED\n")
    assert out(eng, 1) == 7


def test_long_subroutine_name_truncates_consistently():
    # COMPUTE (call) and COMPUTED (definition) both -> COMPUT, so the CALL resolves
    eng = run(IH + "        CALL COMPUTE(5)\n" + END +
              "        SUBROUTINE COMPUTED(N)\n        IMPLICIT INTEGER(A-Z)\n"
              "        COMMON /OUT/ V(40)\n        V(1)=N*2\n" + END)
    assert out(eng, 1) == 10


def test_long_keyword_not_truncated():
    # CONTINUE (8 chars) is a keyword, NOT a symbolic name -> never truncated
    eng = run_int("        DO 5 I=1,3\n  5     CONTINUE\n        V(1)=I\n")
    assert out(eng, 1) == 3            # loop ran; CONTINUE recognized (not "CONTIN")


# ---- EXTERNAL with */& intrinsic override (V5 15.3) ------------------------
_USER_IABS = ("        SUBROUTINE Q\n        END\n"
              "        FUNCTION IABS(N)\n        IMPLICIT INTEGER(A-Z)\n"
              "        IABS=N+100\n" + END)


def test_external_star_overrides_intrinsic():
    eng = run(IH + "        EXTERNAL *IABS\n        V(1)=IABS(5)\n" + END + _USER_IABS)
    assert out(eng, 1) == 105          # user FUNCTION IABS, not the intrinsic


def test_external_ampersand_prefix_also_works():
    eng = run(IH + "        EXTERNAL &IABS\n        V(1)=IABS(5)\n" + END + _USER_IABS)
    assert out(eng, 1) == 105


def test_intrinsic_used_when_not_declared_external():
    # same user FUNCTION present, but without EXTERNAL the intrinsic IABS wins
    eng = run(IH + "        V(1)=IABS(-5)\n" + END + _USER_IABS)
    assert out(eng, 1) == 5            # intrinsic |−5| = 5


# ---- '/' as array-bound delimiter (V5 6.2: synonym for ':') ----------------
def test_slash_as_array_bound_delimiter():
    # W(2/5) means bounds 2:5 -- '/' here is a delimiter, NOT division
    eng = run(IH + "        DIMENSION W(2/5)\n        W(2)=11\n        W(5)=22\n"
              "        V(1)=W(2)\n        V(2)=W(5)\n" + END)
    assert out(eng, 1) == 11
    assert out(eng, 2) == 22


def test_slash_and_colon_bounds_equivalent():
    eng = run(IH + "        DIMENSION A(0:2),B(0/2)\n"
              "        A(2)=7\n        B(2)=7\n        V(1)=A(2)+B(2)\n" + END)
    assert out(eng, 1) == 14


# ---- CONTROL-Z = EOF on terminal input -------------------------------------
def test_control_z_is_eof_on_accept():
    eng = run(IH + "        V(1)=1\n        ACCEPT *, A\n        V(1)=2\n" + END,
              inputs=["\x1a"])
    assert out(eng, 1) == 1            # Ctrl-Z = EOF -> ACCEPT terminated the program
