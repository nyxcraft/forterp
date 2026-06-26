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


def test_formatted_read_from_text_unit_widthless_a_and_slash_multirecord():
    # A formatted READ from a TEXT/card unit must honour both (a) widthless A -- each item reads
    # its own declared CHARACTER length, not one column -- and (b) a `/` that advances to the next
    # record. Regression: FM404 (AFMTS), whose card-reader path lacked both and so read 1 column
    # per A field and could not span records on `A4 / 2A4`.
    src = (
        "      PROGRAM T\n"
        "      CHARACTER C1*1,C2*2,C3*3,D1*4,D2*4,D3*4\n"
        "      READ(5,10) C1,C2,C3\n"
        "   10 FORMAT(A,2A)\n"
        "      READ(5,30) D1,D2,D3\n"
        "   30 FORMAT(A4 / 2A4)\n"
        "      WRITE(6,20) C1,C2,C3,D1,D2,D3\n"
        "   20 FORMAT(A1,1X,A2,1X,A3,1X,A4,1X,A4,1X,A4)\n"
        "      END\n"
    )
    deck = {"lines": ["abcdef", "WXYZ", "AAAABBBB"], "pos": 0, "mode": "r", "text": True}
    eng = run(src, setup=lambda e: e.io.__setitem__(5, deck), dialect=forterp.F77)
    assert printed(eng).strip() == "a bc def WXYZ AAAA BBBB"


def test_a_input_into_a_character_substring_uses_the_window_length():
    # A formatted READ into a CHARACTER substring NAME(lo:hi) is governed by the SUBSTRING
    # length, not the variable's declared length (X3.9-1978 13.5.11): a widthless A reads that
    # many columns, and an explicit A field WIDER than the window supplies its RIGHTMOST chars.
    # Regression: FM901 (AFMTF) -- forterp read 1 column per widthless A and kept the LEFTMOST
    # chars of a too-wide field, so the reconstructed strings were scrambled.
    src = (
        "      PROGRAM T\n"
        "      CHARACTER B43VK*43\n"
        "      COMMON /O/ OUT\n"
        "      CHARACTER OUT*20\n"
        "      READ(5,7) B43VK, B43VK(4:8), B43VK(17:20)\n"
        "    7 FORMAT(A43,A7,A2)\n"
        "      OUT = B43VK(1:20)\n"
        "      END\n"
    )
    deck = {
        "lines": ["TO XXXXX NOT TO XXXX-  THAT IS THE QUESTIONXXBE ORBE"],
        "pos": 0,
        "mode": "r",
        "text": True,
    }
    eng = run(src, setup=lambda e: e.io.__setitem__(5, deck), dialect=forterp.F77)
    # A7 field "XXBE OR" -> rightmost 5 "BE OR" into (4:8); A2 "BE" -> "BE  " into (17:20).
    assert eng.commons["O"] == ["TO BE OR NOT TO BE  "]


def test_io_list_implied_do_leaves_control_var_at_terminal_value():
    # After an I/O-list implied-DO completes, its control variable is left at the terminal value
    # (limit+step), exactly like a DO loop (X3.9-1978 11.10 / 12.8.2.3) -- so (A(I),I=1,5) leaves
    # I=6, not 5. Regression for FM111 test 3, which writes the post-READ loop index.
    src = (
        "        PROGRAM T\n        DIMENSION A(5)\n        COMMON /OUT/ V(2)\n"
        "        READ(5,10) (A(I), I=1,5)\n"
        "   10   FORMAT(5F4.0)\n"
        "        V(1) = I\n        V(2) = A(5)\n        END\n"
    )

    # a fresh deck per run -- run() exercises both dialects and must not share the mutated pos
    def fresh(e):
        e.io[5] = {"lines": ["  1.  2.  3.  4.  5."], "pos": 0, "mode": "r", "text": True}

    eng = run(src, setup=fresh)
    assert [out(eng, 1), out(eng, 2)] == [6, 5.0]


def test_iostat_specifier_is_defined_per_f77_12_7():
    # X3.9-1978 12.7: a READ/WRITE with IOSTAT= defines that variable -- 0 on success, a
    # POSITIVE value on an error, a NEGATIVE value at end-of-file. Regression: forterp parsed
    # IOSTAT= but never assigned it (only INQUIRE used it), so the common IF(IOS.LT.0) EOF /
    # IF(IOS.GT.0) error idiom silently saw a stale 0. Now assigned in the I/O guard.
    src = (
        "      PROGRAM T\n      COMMON /OUT/ V(3)\n      REAL V\n"
        "      OPEN(UNIT=1, STATUS='SCRATCH', FORM='FORMATTED')\n"
        "      WRITE(1,*) 11\n      REWIND 1\n"
        "      READ(1,*,IOSTAT=I1) N1\n"  # success -> 0
        "      READ(1,*,IOSTAT=I2) N2\n"  # EOF -> negative
        "      V(1)=I1\n      V(2)=I2\n      V(3)=N1\n      END\n"
    )
    eng = run(src, dialect=forterp.F77)
    i1, i2, n1 = (out(eng, i) for i in (1, 2, 3))
    assert i1 == 0 and i2 < 0 and n1 == 11

    # a numeric conversion error -> positive IOSTAT, and ERR= takes the branch
    src = (
        "      PROGRAM T\n      COMMON /OUT/ V(2)\n      REAL V\n      CHARACTER*5 S\n"
        "      S='ABCDE'\n"
        "      READ(S,'(I5)',IOSTAT=IOS,ERR=90) N\n      V(2)=0\n      GO TO 99\n"
        "   90 V(2)=1\n   99 V(1)=IOS\n      END\n"
    )
    eng = run(src, dialect=forterp.F77)
    assert out(eng, 1) > 0 and out(eng, 2) == 1
