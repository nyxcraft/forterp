"""FORTRAN-10 V5 logical value model (Ch 4): relationals yield -1/0, the logical
operators are BITWISE on the 36-bit word, and truth is sign-based (.TRUE. = -1).
"""

from conftest import out, run, run_int

IH = "        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n        COMMON /OUT/ V(40)\n"
END = "        END\n"


def test_relational_yields_minus_one_and_zero():
    eng = run_int(
        "        V(1)=(3==3)\n        V(2)=(3==4)\n        V(3)=(5>2)\n        V(4)=(5<2)\n"
    )
    assert [out(eng, i) for i in range(1, 5)] == [-1, 0, -1, 0]


def test_logical_operators_are_bitwise():
    eng = run_int(
        "        V(1)=6.AND.3\n        V(2)=6.OR.1\n"
        "        V(3)=5.XOR.3\n        V(4)=.NOT.0\n        V(5)=.NOT.(-1)\n"
    )
    assert out(eng, 1) == 2  # 110 & 011 = 010
    assert out(eng, 2) == 7  # 110 | 001 = 111
    assert out(eng, 3) == 6  # 101 ^ 011 = 110
    assert out(eng, 4) == -1  # ~0  = all ones
    assert out(eng, 5) == 0  # ~-1 = 0


def test_or_matches_manual_octal_example():
    # V5 manual p4-7: A = "456 .OR. "201  (bit-by-bit OR)
    eng = run_int('        V(1)="456.OR."201\n')
    assert out(eng, 1) == (0o456 | 0o201)


def test_eqv_is_bitwise_equivalence():
    eng = run_int("        V(1)=(-1).EQV.(-1)\n        V(2)=(-1).EQV.0\n")
    assert out(eng, 1) == -1  # XNOR of equal bit patterns -> all ones
    assert out(eng, 2) == 0


def test_truth_is_sign_based_in_logical_if():
    # .TRUE.=-1 (negative) takes the branch; .FALSE.=0 does not; a *positive*
    # value is .FALSE. under the sign rule (unusual, but it's the V5 semantics).
    eng = run(
        "        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n        LOGICAL L\n"
        "        COMMON /OUT/ V(40)\n        V(1)=0\n        V(2)=0\n        V(3)=0\n"
        "        L=.TRUE.\n        IF(L) V(1)=1\n"
        "        L=.FALSE.\n        IF(L) V(2)=1\n"
        "        IF(.NOT..FALSE.) V(3)=1\n" + END
    )
    assert [out(eng, i) for i in range(1, 4)] == [1, 0, 1]


def test_or_binds_tighter_than_eqv_and_xor():
    # V5 Table 4-7: .OR. is level 8, .EQV./.XOR. are level 9 (looser).
    # So  A .EQV. B .OR. C  parses as  A .EQV. (B .OR. C).
    # With A=0, B=0, C=-1:  0 .EQV. (0 .OR. -1) = 0 .EQV. -1 = 0  (correct grouping);
    # the wrong grouping (0 .EQV. 0) .OR. -1 would give -1.
    eng = run_int(
        "        A=0\n        B=0\n        C=-1\n"
        "        V(1)=A.EQV.B.OR.C\n"
        "        V(2)=A.XOR.B.OR.C\n"
    )
    assert out(eng, 1) == 0  # .OR. evaluated before .EQV.
    assert out(eng, 2) == -1  # 0 .XOR. (0 .OR. -1) = 0 .XOR. -1 = -1


def test_logical_ops_on_relationals_drive_if_correctly():
    # a common pattern: logical ops over relational operands inside IF
    body = (
        "        V(1)=0\n        V(2)=0\n        V(3)=0\n"
        "        IF((3==3).AND.(4>1)) V(1)=1\n"
        "        IF((3==4).OR.(9>2)) V(2)=1\n"
        "        IF((3==4).AND.(9>2)) V(3)=1\n"
    )
    eng = run_int(body)
    assert [out(eng, i) for i in range(1, 4)] == [1, 1, 0]
