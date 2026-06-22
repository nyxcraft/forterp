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
    eng = forterp.fortran10.build_engine(forterp.fortran10.parse_text(src)[0], root=root)
    eng.run_program("T")
    assert json.load(open(os.path.join(root, "X.DAT"))) == [[10], [20], [99]]


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
