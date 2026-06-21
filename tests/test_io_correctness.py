"""I/O correctness regressions found by differential testing against gfortran: the
list-directed input grammar (r*c repeat, / terminator) and sequential-file repositioning
(BACKSPACE/REWIND then WRITE replaces the record rather than appending)."""

import json
import os
import tempfile

import forterp
from conftest import HEAD, TAIL, out, run


def test_list_directed_repeat_count_and_slash_terminator():
    # '3*7' repeats 7 three times; '8' fills the 4th; '/' ends the read, so A(5) keeps -1.
    src = HEAD + (
        "        DIMENSION A(5)\n"
        "        DO 5 I=1,5\n"
        "    5   A(I) = -1\n"
        "        READ(5,*) A\n"
        "        DO 6 I=1,5\n"
        "    6   V(I) = A(I)\n"
    ) + TAIL
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
