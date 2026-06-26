"""I/O correctness regressions found by differential testing against gfortran: the
list-directed input grammar (r*c repeat, / terminator) and sequential-file repositioning
(BACKSPACE/REWIND then WRITE replaces the record rather than appending)."""

import json
import os
import tempfile

import pytest
from conftest import HEAD, TAIL, out, printed, run

import forterp


def test_list_directed_repeat_count_and_slash_terminator():
    # '3*7' repeats 7 three times; '8' fills the 4th; '/' ends the read, so A(5) keeps -1.
    src = (
        HEAD
        + (
            "        DIMENSION A(5)\n"
            "        DO 5 I=1,5\n"
            "    5   A(I) = -1\n"
            "        READ(5,*) A\n"
            "        DO 6 I=1,5\n"
            "    6   V(I) = A(I)\n"
        )
        + TAIL
    )
    eng = run(src, inputs=["3*7 8 /"], dialect=forterp.FORTRAN10)
    assert [out(eng, i) for i in range(1, 6)] == [7, 7, 7, 8, -1]


def test_backspace_then_write_replaces_the_record():
    # ANSI X3.9-1966 7.1.3.3: a WRITE after BACKSPACE replaces the record and truncates
    # what followed -- it must not append.
    src = (
        "      PROGRAM T\n"
        "      OPEN(UNIT=1, ACCESS='SEQOUT', FILE='X.DAT')\n"
        "      WRITE(1) 10\n      WRITE(1) 20\n      WRITE(1) 30\n"
        "      BACKSPACE 1\n      WRITE(1) 99\n      CLOSE(1)\n      END\n"
    )
    root = tempfile.mkdtemp()
    # BACKSPACE semantics are backend-agnostic; keep the portable (JSON) file backend so we can
    # inspect it directly (forterp.fortran10 now defaults forots=True -> binary, so opt out here).
    eng = forterp.fortran10.build_engine(
        forterp.fortran10.parse_text(src)[0], root=root, forots=False
    )
    eng.run_program("T")
    assert json.load(open(os.path.join(root, "X.DAT"))) == [[10], [20], [99]]


def test_unformatted_complex_round_trips_through_the_file_store():
    # A COMPLEX value written to an unformatted file must survive CLOSE + re-OPEN + READ.
    # Regression: the portable (JSON) record store could not serialize a Python complex
    # (TypeError: Object of type complex is not JSON serializable) -- now tagged as [re, im].
    src = (
        "      PROGRAM T\n      COMPLEX Z\n      COMMON /O/ ZR, ZI\n"
        "      OPEN(UNIT=1, ACCESS='SEQOUT', FILE='Z.DAT')\n"
        "      WRITE(1) (3.5, -2.25)\n      CLOSE(1)\n"
        "      OPEN(UNIT=1, ACCESS='SEQIN', FILE='Z.DAT')\n"
        "      READ(1) Z\n      CLOSE(1)\n      ZR = REAL(Z)\n      ZI = AIMAG(Z)\n      END\n"
    )
    root = tempfile.mkdtemp()
    eng = forterp.fortran10.build_engine(  # portable JSON backend (forots binary path is separate)
        forterp.fortran10.parse_text(src)[0], root=root, forots=False
    )
    eng.run_program("T")
    assert eng.commons["O"] == [3.5, -2.25]
    # the on-disk record persisted the complex as a tagged [re, im] pair
    assert json.load(open(os.path.join(root, "Z.DAT"))) == [[{"__complex__": [3.5, -2.25]}]]


def test_decode_of_a_malformed_field_raises_a_conversion_error():
    # DECODE (internal formatted READ) routes a bad numeric field through the same
    # conversion error as a real READ -- a clean error, not a crash.
    src = (
        "        PROGRAM T\n        DIMENSION BUF(2)\n        DATA BUF /5HABCDE,5H    Z/\n"
        "        DECODE(10,100,BUF) I\n  100   FORMAT(I5)\n        END\n"
    )
    with pytest.raises(forterp.fmt.InputConversionError):
        run(src, dialect=forterp.FORTRAN10)


def test_carriage_control_honored_per_reverted_record_end_to_end():
    # a reverting FORMAT emits three records to unit 6; each record's '0' (double-space)
    # control character is honored, not just the first record's.
    src = "        PROGRAM T\n        WRITE(6,5) 1,2,3\n    5   FORMAT('0',I2)\n        END\n"
    eng = run(src, dialect=forterp.FORTRAN10)
    assert printed(eng) == "\n 1\n\n 2\n\n 3\n"


def test_stmt_function_wrong_arg_count_is_clean(capsys):
    # too many actuals to a statement function is a clean error, not a silently-ignored arg.
    import os
    import tempfile

    from forterp.cli import main

    with tempfile.NamedTemporaryFile("w", suffix=".FOR", delete=False) as f:
        f.write(
            "      PROGRAM T\n      F(X)=X+1.0\n      Y=F(2.0,3.0)\n"
            "      WRITE(6,9) INT(Y)\n    9 FORMAT(I6)\n      END\n"
        )
        path = f.name
    try:
        rc = main(["--std", "fortran10", path])
    finally:
        os.unlink(path)
    err = capsys.readouterr().err
    assert rc == 1 and "Traceback" not in err and "statement function" in err


def test_list_directed_input_complex_and_d_exponent_spanning_records():
    # List-directed READ accepts a D/d exponent (2.5D0) and a COMPLEX (re,im) constant, which may
    # SPAN records -- here C = (3.0,4.0) is split across two cards (X3.9-1978 13.6.2/13.6.3).
    # Regression: FM906 (LSTDI2), which used to error on the D exponent and the parenthesised value.
    src = (
        "        PROGRAM T\n        COMMON /OUT/ V(40)\n        REAL V\n        COMPLEX C\n"
        "        READ(5,*) X, C\n"
        "        V(1)=X\n        V(2)=REAL(C)\n        V(3)=AIMAG(C)\n        END\n"
    )
    deck = {"lines": ["2.5D0  (3.0,", "4.0)"], "pos": 0, "mode": "r", "text": True}
    eng = run(src, setup=lambda e: e.io.__setitem__(5, deck), dialect=forterp.FORTRAN10)
    assert [out(eng, i) for i in range(1, 4)] == [2.5, 3.0, 4.0]
