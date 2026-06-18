"""Character/Hollerith handling end-to-end: DATA char arrays, comparisons."""

from conftest import run, out
from f66.parser import pack5

CHARHEAD = (
    "        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n"
    "        COMMON /OUT/ V(40)\n        DIMENSION OK(5)\n"
    "        DATA OK/'+',' ','O','*','X'/\n"
)


def test_char_data_stored_as_packed_words():
    eng = run(CHARHEAD + "        V(1)=OK(1)\n        V(2)=OK(3)\n        END\n")
    assert out(eng, 1) == pack5("+")
    assert out(eng, 2) == pack5("O")


def test_char_array_element_comparison():
    body = (
        "        V(1)=0\n        V(2)=0\n        V(3)=0\n"
        "        IF(OK(1)=='+') V(1)=1\n"
        "        IF(OK(5)=='X') V(2)=1\n"
        "        IF(OK(2)==' ') V(3)=1\n        END\n"
    )
    eng = run(CHARHEAD + body)
    assert [out(eng, i) for i in range(1, 4)] == [1, 1, 1]


def test_char_literal_assignment_and_compare():
    eng = run(
        "        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n"
        "        COMMON /OUT/ V(40)\n        C='Q'\n        V(1)=0\n"
        "        IF(C=='Q') V(1)=1\n        IF(C#'Z') V(2)=1\n        END\n"
    )
    assert out(eng, 1) == 1
    assert out(eng, 2) == 1


def test_hollerith_count_marker_is_case_insensitive():
    # FORTRAN is case-insensitive, so nH and nh are both Hollerith. The lexer used to
    # only accept uppercase 'H', so '1hC' parsed as the integer 1 (-> blanks) -- which
    # broke real code that used lowercase Hollerith (e.g. tknlst(i)=1hc).
    eng = run(
        "        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n"
        "        COMMON /OUT/ V(40)\n"
        "        V(1)=1hC\n        V(2)=1HC\n        V(3)='C'\n"
        "        V(4)=3habc\n        V(5)=3HABC\n        END\n"
    )
    assert out(eng, 1) == out(eng, 2) == out(eng, 3) == pack5("C")  # 1hC == 1HC == 'C'
    assert out(eng, 4) == pack5("abc") and out(eng, 5) == pack5("ABC")  # case kept in body


def test_double_quote_char_is_octal_not_string():
    # "101 is octal 65 = ASCII 'A'; ensure octal parse, then compare as packed char
    eng = run(
        "        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n"
        '        COMMON /OUT/ V(40)\n        V(1)="101\n        END\n'
    )
    assert out(eng, 1) == 65
