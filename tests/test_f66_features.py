"""General FORTRAN-66 features for broad coverage (beyond a minimal subset, but a
conformant F66 interpreter should support them): statement functions, PAUSE, ASSIGN/
assigned GOTO, type size modifiers, blank common, Hollerith nH literals, multiple
RETURN."""

from conftest import out, printed, run, run_int

from forterp.parser import pack5

IH = "        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n        COMMON /OUT/ V(40)\n"
END = "        END\n"


# ---- statement functions ---------------------------------------------------
def test_single_arg_statement_function():
    eng = run(IH + "        SQ(X)=X*X\n        V(1)=SQ(5)\n        V(2)=SQ(9)\n" + END)
    assert out(eng, 1) == 25
    assert out(eng, 2) == 81


def test_two_arg_statement_function():
    eng = run(IH + "        ADD(A,B)=A+B*2\n        V(1)=ADD(3,4)\n" + END)
    assert out(eng, 1) == 11


def test_statement_function_uses_unit_variables():
    # M and B are ordinary unit variables; the statement function closes over them
    eng = run(IH + "        LIN(X)=M*X+B\n        M=3\n        B=1\n        V(1)=LIN(10)\n" + END)
    assert out(eng, 1) == 31


def test_statement_function_dummy_does_not_clobber_unit_var():
    eng = run(IH + "        SQ(X)=X*X\n        X=99\n        V(1)=SQ(5)\n        V(2)=X\n" + END)
    assert out(eng, 1) == 25
    assert out(eng, 2) == 99  # the unit's X is restored after the call


def test_nested_statement_functions():
    eng = run(IH + "        F(X)=X+1\n        G(X)=F(X)*2\n        V(1)=G(3)\n" + END)
    assert out(eng, 1) == 8  # G(3) = (3+1)*2


def test_array_assignment_not_misread_as_statement_function():
    # V is dimensioned, so V(1)=... is an array store, never a statement function
    eng = run(IH + "        DIMENSION W(3)\n        W(1)=7\n        V(1)=W(1)\n" + END)
    assert out(eng, 1) == 7


# ---- ASSIGN + assigned GOTO ------------------------------------------------
def test_assign_and_assigned_goto():
    src = (
        "        V(1)=0\n        ASSIGN 200 TO N\n        GOTO N\n        V(1)=99\n  200   V(1)=7\n"
    )
    assert out(run_int(src), 1) == 7  # jumped to 200, skipped the 99


def test_assigned_goto_reassignment():
    # the variable holds the active label; reassigning changes the jump target
    src = (
        "        ASSIGN 10 TO N\n        GOTO 5\n"
        "  10    V(1)=1\n        GOTO 99\n"
        "  20    V(1)=2\n        GOTO 99\n"
        "  5     ASSIGN 20 TO N\n        GOTO N\n"
        "  99    CONTINUE\n"
    )
    assert out(run_int(src), 1) == 2  # N reassigned to 20 before the jump


def test_assigned_goto_with_label_list():
    # the optional ,(label-list) is advisory; the jump still uses the stored label
    src = (
        "        ASSIGN 30 TO L\n        GOTO L,(10,20,30)\n"
        "  10    V(1)=1\n        GOTO 99\n"
        "  30    V(1)=3\n  99    CONTINUE\n"
    )
    assert out(run_int(src), 1) == 3


def test_assigned_goto_label_list_without_a_comma():
    # The comma before the advisory label list is optional (X3.9-1966 10.3): `GO TO L (10,20,30)`.
    src = (
        "        ASSIGN 20 TO L\n        GO TO L (10,20,30)\n"
        "  10    V(1)=1\n        GOTO 99\n"
        "  20    V(1)=2\n  99    CONTINUE\n"
    )
    assert out(run_int(src), 1) == 2


def test_keyword_prefixed_assignment_is_not_a_statement():
    # F66 blanks-insignificance (X3.9-1966 7.1.2.1.1): a statement with a top-level '=' is an
    # ASSIGNMENT, even when it begins with keyword-like text. `GO TO 1 = 43` assigns the variable
    # GOTO1, and `CALL FL = 62` assigns CALLFL -- neither is a GO TO / CALL. (Regression: FM010,
    # where mis-parsing `GO TO 1 = 4 3.` as a jump skipped to the wrong test and corrupted output.)
    eng = run_int(
        "        GO TO 1 = 43\n        CALL FL = 62\n        V(1) = GOTO1\n        V(2) = CALLFL\n"
    )
    assert out(eng, 1) == 43 and out(eng, 2) == 62


# ---- PAUSE -----------------------------------------------------------------
def test_pause_does_not_halt_execution():
    eng = run_int("        V(1)=1\n        PAUSE\n        V(1)=2\n")
    assert out(eng, 1) == 2  # statement after PAUSE ran


def test_pause_with_code_emits_and_continues():
    eng = run(IH + "        V(1)=1\n        PAUSE 77\n        V(1)=2\n" + END)
    assert out(eng, 1) == 2
    assert "PAUSE 77" in "".join(eng.out)


# ---- type size modifiers ---------------------------------------------------
def test_type_size_modifiers():
    eng = run(
        "        PROGRAM T\n        REAL*8 D\n        INTEGER*2 I\n        REAL A,B*8\n"
        "        COMMON /OUT/ V(40)\n        REAL V\n"
        "        D=3\n        I=7\n        A=2.5\n        B=4\n"
        "        V(1)=D*2\n        V(2)=I\n        V(3)=B\n" + END
    )
    assert out(eng, 1) == 6.0  # REAL*8 = double
    assert out(eng, 2) == 7.0  # INTEGER*2 = integer
    assert out(eng, 3) == 4.0  # per-variable B*8 = double


# ---- blank / unlabeled common ----------------------------------------------
def test_blank_common():
    eng = run(
        "        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n"
        "        COMMON X,Y\n        COMMON /OUT/ V(40)\n"
        "        X=11\n        Y=22\n        V(1)=X+Y\n" + END
    )
    assert out(eng, 1) == 33
    eng2 = run(
        "        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n"
        "        COMMON //P,Q\n        COMMON /OUT/ V(40)\n"
        "        P=5\n        Q=6\n        V(1)=P*Q\n" + END
    )
    assert out(eng2, 1) == 30


# ---- Hollerith nH literals -------------------------------------------------
def test_hollerith_nh_literals():
    eng = run(
        IH + "        DATA C/2HAB/\n        V(1)=0\n"
        "        IF(C==2HAB) V(1)=1\n        V(2)=C\n" + END
    )
    assert out(eng, 1) == 1
    assert out(eng, 2) == pack5("AB")


def test_hollerith_preserves_spaces_and_count():
    eng = run(IH + "        V(1)=0\n        IF(5HHELLO==5HHELLO) V(1)=1\n" + END)
    assert out(eng, 1) == 1


def test_do_var_h_not_misread_as_hollerith():
    # a space before H (DO 5 H=...) must NOT be taken as a Hollerith count
    eng = run_int("        N=0\n        DO 5 H=1,3\n  5     N=N+H\n        V(1)=N\n")
    assert out(eng, 1) == 6


# ---- multiple / alternate RETURN -------------------------------------------
_ALT = (
    "        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n        COMMON /OUT/ V(40)\n"
    "        V(1)=0\n        CALL SUB(2,$100,$200)\n        V(1)=9\n        GOTO 999\n"
    "  100   V(1)=1\n        GOTO 999\n  200   V(1)=2\n  999   CONTINUE\n        END\n"
    "        SUBROUTINE SUB(K,*,*)\n        RETURN K\n        END\n"
)


def test_alternate_return_selects_label():
    assert out(run(_ALT), 1) == 2  # RETURN 2 -> 2nd label ($200)
    assert out(run(_ALT.replace("RETURN K", "RETURN 1")), 1) == 1


def test_alternate_return_out_of_range_is_normal_return():
    assert out(run(_ALT.replace("RETURN K", "RETURN 5")), 1) == 9


def test_alternate_return_ampersand_label_constant():
    # V5 3.2.8: a statement-label constant may be written $n OR &n
    assert out(run(_ALT.replace("$100,$200", "&100,&200")), 1) == 2


# ---- STOP with a message (V5 9.6) ------------------------------------------
def test_stop_with_message_prints_then_halts():
    eng = run(
        "        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n"
        "        COMMON /OUT/ V(40)\n        V(1)=1\n        STOP 'ALL DONE'\n"
        "        V(1)=2\n        END\n"
    )
    assert "ALL DONE" in "".join(eng.out)
    assert out(eng, 1) == 1  # the statement after STOP did not run


def test_bare_stop_halts_silently():
    eng = run(
        "        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n"
        "        COMMON /OUT/ V(40)\n        V(1)=1\n        STOP\n"
        "        V(1)=2\n        END\n"
    )
    assert out(eng, 1) == 1


# ---- list-directed I/O -----------------------------------------------------
def test_list_directed_output():
    eng = run(
        "        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n        REAL X\n"
        "        I=42\n        X=3.5\n        TYPE *, I, X\n        PRINT *, I\n" + END
    )
    assert "".join(eng.out) == " 42 3.5\n 42\n"


def test_list_directed_input():
    eng = run(
        IH + "        ACCEPT *, A, B, C\n        V(1)=A\n        V(2)=B\n        V(3)=C\n" + END,
        inputs=["10 20 30"],
    )
    assert [out(eng, i) for i in range(1, 4)] == [10, 20, 30]


# ---- run-time FORMAT held in an array (F66 7.2.3.10) -----------------------
# A FORMAT identifier may be an array (or variable) holding the format text as
# Hollerith characters, read when the I/O statement executes. The format text is
# taken from the first element onward until its parentheses balance.
def test_format_held_in_array():
    eng = run(
        "        PROGRAM T\n        DIMENSION IFMT(2)\n"
        "        DATA IFMT /4H(I5),4H    /\n"
        "        WRITE(6,IFMT) 42\n" + END
    )
    # I5 of 42 is '   42'; its leading blank is the carriage control (consumed)
    assert printed(eng) == "  42\n"


def test_format_assembled_across_array_elements():
    # the spec spans two Hollerith words: '(I5,' + 'I3)'
    eng = run(
        "        PROGRAM T\n        DIMENSION IFMT(2)\n"
        "        DATA IFMT /4H(I5,,3HI3)/\n"
        "        WRITE(6,IFMT) 42, 7\n" + END
    )
    assert printed(eng) == "  42  7\n"


# ---- Hollerith field read on input persists into the FORMAT (F66 7.2.3.8) --
# Reading into an nH field overwrites its text; re-using the same FORMAT on a later
# WRITE echoes what was read (the classic "variable heading" idiom).
def test_hollerith_field_read_then_echoed():
    eng = run(
        "        PROGRAM T\n        READ(5,20)\n        WRITE(6,20)\n"
        "  20    FORMAT(1H ,4Hwxyz)\n" + END,
        inputs=[" ABCD"],
    )
    assert printed(eng) == "ABCD\n"  # leading-blank carriage control consumed


# ---- FORTRAN-10 V5 double-precision + degree-argument math intrinsics -------
def test_v5_double_and_degree_intrinsics():
    # the V5 superset math library: double-precision elementary (DTAN/DASIN/DSINH/…,
    # DPROD/DNINT/IDNINT/DINT/DDIM) and degree-argument (TAND/ASIND/ATAN2D/…) functions.
    src = (
        "        PROGRAM T\n        COMMON /OUT/ V(40)\n"  # V defaults REAL
        "        V(1) = DPROD(3.0, 4.0)\n"
        "        V(2) = DNINT(3.5)\n"
        "        V(3) = TAND(45.0)\n"
        "        V(4) = ATAN2D(1.0, 1.0)\n"
        "        V(5) = IDNINT(2.5)\n"
        "        V(6) = DSINH(0.0)\n" + END
    )
    eng = run(src)
    assert out(eng, 1) == 12.0  # DPROD
    assert out(eng, 2) == 4.0  # DNINT
    assert abs(out(eng, 3) - 1.0) < 1e-9  # TAND(45)
    assert out(eng, 4) == 45.0  # ATAN2D(1,1)
    assert out(eng, 5) == 3.0  # IDNINT(2.5) -> halves away from zero
    assert out(eng, 6) == 0.0  # DSINH(0)


def test_rot_word_rotate_intrinsic():
    # V5 ROT: logical word rotate within the target word (PDP-10 36-bit under run_int)
    eng = run_int("        V(1) = ROT(1, 1)\n        V(2) = ROT(2, -1)\n")
    assert out(eng, 1) == 2  # rotate left 1
    assert out(eng, 2) == 1  # rotate right 1


# ---- adjustable (dummy-arg) array dimensions -------------------------------
def test_adjustable_dimensions():
    src = (
        "        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n        COMMON /OUT/ V(40)\n"
        "        DIMENSION M(2,3)\n        DATA M/10,20,30,40,50,60/\n"
        "        CALL GET(M,2,3)\n        END\n"
        "        SUBROUTINE GET(A,NR,NC)\n        IMPLICIT INTEGER(A-Z)\n"
        "        DIMENSION A(NR,NC)\n        COMMON /OUT/ V(40)\n"
        "        V(1)=A(1,1)\n        V(2)=A(2,1)\n        V(3)=A(1,2)\n        V(4)=A(2,3)\n"
        "        END\n"
    )
    eng = run(src)
    assert [out(eng, i) for i in range(1, 5)] == [10, 20, 30, 60]


# ---- literal-spanning DATA -------------------------------------------------
def test_literal_spanning_data():
    from forterp.fmt import unpack_chars

    eng = run(
        IH + "        DATA X,Y,Z/'ABCDEFGHIJKL'/\n"
        "        V(1)=X\n        V(2)=Y\n        V(3)=Z\n" + END
    )
    assert [unpack_chars(out(eng, i), 5) for i in range(1, 4)] == ["ABCDE", "FGHIJ", "KL   "]


# ---- device control --------------------------------------------------------
def test_device_control_record_positioning():
    import forterp.ast_nodes as A
    from forterp.engine import Engine

    eng = Engine({})
    eng.io[1] = {"recs": [10, 20, 30], "pos": 2, "mode": "r"}
    eng._file_ctl(A.FileCtl(verb="REWIND", specs={"UNIT": 1}), None)
    assert eng.io[1]["pos"] == 0
    eng.io[1]["pos"] = 2
    eng._file_ctl(A.FileCtl(verb="BACKSPACE", specs={"UNIT": 1}), None)
    assert eng.io[1]["pos"] == 1
    eng._file_ctl(A.FileCtl(verb="SKIPREC", specs={"UNIT": 1}), None)
    assert eng.io[1]["pos"] == 2
    eng.io[1]["pos"] = 1
    eng._file_ctl(A.FileCtl(verb="ENDFILE", specs={"UNIT": 1}), None)
    # ENDFILE writes an endfile marker at pos (truncating data after it) and positions past it;
    # a following BACKSPACE backs over the MARKER, not record 10 (X3.9-1978 12.10.4).
    from forterp.engine import ENDFILE_MARK

    assert eng.io[1]["recs"] == [10, ENDFILE_MARK]
    assert eng.io[1]["pos"] == 2
    eng._file_ctl(A.FileCtl(verb="BACKSPACE", specs={"UNIT": 1}), None)
    assert eng.io[1]["pos"] == 1  # positioned at the marker, after record 10


def test_endfile_then_backspace_does_not_clobber_a_record():
    # X3.9-1978 12.10.4 (FM411): ENDFILE writes an endfile record; a BACKSPACE then backs over
    # THAT marker, not a data record. Write 3 records, ENDFILE, BACKSPACE, write 2 more, rewind
    # and count -> 5 (the endfile-then-write must not overwrite the 3rd record).
    src = (
        "        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n        COMMON /O/ N\n"
        "        DO 1 I=1,3\n    1   WRITE(9) I\n"
        "        ENDFILE 9\n        BACKSPACE 9\n"
        "        WRITE(9) 4\n        WRITE(9) 5\n"
        "        REWIND 9\n        N=0\n"
        "        DO 2 I=1,50\n        READ(9,END=3) K\n    2   N=N+1\n"
        "    3   CONTINUE\n" + END
    )
    eng = run(src)
    assert eng.commons["O"][0] == 5


def test_zero_argument_statement_function():
    # FM311: a statement function may take ZERO dummy arguments -- F() = expr; R = F() uses the
    # current value of the body. Previously F() was mis-parsed as an array reference.
    src = (
        "        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n        COMMON /OUT/ V(8)\n"
        "        F() = K\n        K = 7\n        V(1) = F()\n" + END
    )
    assert out(run(src), 1) == 7


def test_statement_function_dummy_shadows_enclosing_function_dummy():
    # FM311: a statement function dummy with the SAME NAME as the enclosing function's dummy
    # argument shadows it inside the SF body. G(X)=X+1 with FUNCTION FF(X): G(10.) must use 10.,
    # not FF's X (5.5). So FF(5.5) = 5.5 + (10.+1.) = 16.5, not 5.5 + (5.5+1.) = 12.0.
    src = (
        "        PROGRAM T\n        COMMON /OUT/ V(8)\n        REAL V\n"
        "        V(1) = FF(5.5)\n        END\n"
        "        REAL FUNCTION FF(X)\n        G(X) = X + 1.0\n"
        "        Y = G(10.0)\n        FF = X + Y\n        RETURN\n        END\n"
    )
    assert abs(out(run(src), 1) - 16.5) < 1e-4


def test_assigned_format_label_in_write():
    # FM252 / F66 7.2.3.10: an INTEGER variable ASSIGNed a FORMAT label is a valid format
    # reference -- WRITE(u, I) uses FORMAT statement I, not the variable's bits as Hollerith.
    src = (
        "        PROGRAM T\n        ASSIGN 10 TO IFMT\n"
        "  10    FORMAT(' HI=',I3)\n        WRITE(6,IFMT) 42\n" + END
    )
    assert printed(run(src)) == "HI= 42\n"


def test_multi_statement_common_concatenates_and_associates_positionally():
    # FM302 / F66 7.2.1.2: successive COMMON statements for the same block APPEND (they don't
    # restart at offset 0). The main fills blank COMMON across three statements; the subroutine
    # views the same storage under different names/shape (renaming) -- association is positional.
    src = (
        "        PROGRAM T\n        IMPLICIT INTEGER (A-Z)\n        COMMON /O/ N\n"
        "        COMMON IA\n        COMMON IB, IC\n        COMMON ID\n"
        "        IA=10\n        IB=20\n        IC=30\n        ID=40\n"
        "        CALL SUB\n"
        "        N = IA*1 + IB*2 + IC*3 + ID*4\n"  # SUB doubled each via a 4-array view
        "        END\n"
        "        SUBROUTINE SUB\n        IMPLICIT INTEGER (A-Z)\n"
        "        COMMON K(4)\n"  # the 4 blank-COMMON words seen as one array
        "        DO 1 I=1,4\n    1   K(I) = K(I) * 2\n"
        "        END\n"
    )
    eng = run(src)
    # after SUB: IA=20, IB=40, IC=60, ID=80 -> 20 + 80 + 180 + 320 = 600
    assert eng.commons["O"][0] == 600


# ---- default-device I/O, PUNCH, REREAD -------------------------------------
def test_punch_and_default_device_write():
    eng = run(
        "        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n        I=7\n"
        "        PUNCH *, I\n        WRITE 100, I\n  100   FORMAT(' N=',I3)\n" + END
    )
    # PUNCH list-directed " 7\n"; then WRITE's ' ' carriage control is consumed
    # (single advance) and the record ends with its trailing newline -> no blank line
    assert "".join(eng.out) == " 7\nN=  7\n"


def test_default_device_read_and_reread():
    eng = run(
        IH + "        READ *, A\n        REREAD *, B, C\n"
        "        V(1)=A\n        V(2)=B\n        V(3)=C\n" + END,
        inputs=["11 22 33"],
    )
    assert [out(eng, i) for i in range(1, 4)] == [11, 11, 22]  # REREAD re-reads the record


# ---- COMMON sized by a separate DIMENSION statement ------------------------
# F66 lets a COMMON member be dimensioned in a later DIMENSION (or type) stmt.
# The block must reserve the FULL array, not one word per name -- e.g. COMMON
# /BLK/ KTAB,ATAB,SIZ with DIMENSION KTAB(300),ATAB(300), as the test below shows.
def test_common_dimensioned_by_separate_statement():
    eng = run(
        IH + "        COMMON /BLK/ KTAB,ATAB,SIZ\n"
        "        DIMENSION KTAB(300),ATAB(300)\n"
        "        DO 5 I=1,6\n        KTAB(I)=I*10\n  5     ATAB(I)=I*100\n"
        "        SIZ=300\n"
        "        DO 6 I=1,6\n        V(I)=KTAB(I)\n  6     V(I+6)=ATAB(I)\n"
        "        V(13)=SIZ\n" + END
    )
    assert [out(eng, i) for i in range(1, 7)] == [10, 20, 30, 40, 50, 60]
    assert [out(eng, i) for i in range(7, 13)] == [100, 200, 300, 400, 500, 600]
    assert out(eng, 13) == 300  # SIZ not clobbered by KTAB/ATAB overlap


# ---- procedure passed as an argument (F66 8.3, dummy procedure) -------------
# EXTERNAL declares a procedure name; passing it binds a dummy procedure that the
# callee invokes via CALL <dummy>(...) -- the test below passes an EXTERNAL
# routine as an argument and calls it through the dummy.
def test_subroutine_passed_as_argument():
    src = (
        IH
        + "        EXTERNAL SETIT\n        CALL APPLY(SETIT,7)\n"
        + END
        + "        SUBROUTINE APPLY(PROC,N)\n        IMPLICIT INTEGER(A-Z)\n"
        "        CALL PROC(N)\n        RETURN\n        END\n"
        "        SUBROUTINE SETIT(N)\n        IMPLICIT INTEGER(A-Z)\n"
        "        COMMON /OUT/ V(40)\n        V(1)=N*11\n        RETURN\n        END\n"
    )
    eng = run(src)
    assert out(eng, 1) == 77  # APPLY called SETIT(7) through the dummy


def test_function_passed_as_argument():
    src = (
        IH
        + "        EXTERNAL DBL\n        V(1)=USE(DBL,8)\n"
        + END
        + "        INTEGER FUNCTION USE(F,N)\n        IMPLICIT INTEGER(A-Z)\n"
        "        USE=F(N)+1\n        RETURN\n        END\n"
        "        INTEGER FUNCTION DBL(N)\n        IMPLICIT INTEGER(A-Z)\n"
        "        DBL=N*2\n        RETURN\n        END\n"
    )
    eng = run(src)
    assert out(eng, 1) == 17  # USE evaluated DBL(8)=16, +1


# ---- ACCEPT strips the line terminator before the formatted read -----------
# The terminal newline is not record data; an A5 field must not absorb it
# (else a word read from "NO\n" won't compare equal to the literal 'NO').
def test_accept_strips_line_terminator():
    eng = run(
        IH + "        DIMENSION A(4)\n        ACCEPT 3,(A(I),I=1,4)\n"
        "  3     FORMAT(4A5)\n        V(1)=0\n"
        "        IF(A(1).EQ.'NO')V(1)=20\n" + END,
        inputs=["NO\n"],
    )
    assert out(eng, 1) == 20  # 'NO   ' read == literal 'NO'


# ---- consecutive single-space records are single-spaced --------------------
def test_consecutive_records_single_spaced():
    eng = run("        PROGRAM T\n        TYPE 1\n        TYPE 1\n  1     FORMAT(' LINE')\n" + END)
    assert "".join(eng.out) == "LINE\nLINE\n"  # not "\nLINE\n\nLINE\n"


def test_adjustable_array_write_through():
    # writing through an adjustable dummy modifies the caller's array (pass by reference).
    src = (
        IH + "        DIMENSION A(3)\n        DATA A/1,2,3/\n        CALL SETIT(A,3)\n"
        "        V(1)=A(1)\n        V(2)=A(2)\n        V(3)=A(3)\n"
        + END
        + "        SUBROUTINE SETIT(B,N)\n        IMPLICIT INTEGER(A-Z)\n"
        "        DIMENSION B(N)\n        B(2)=99\n" + END
    )
    eng = run(src)
    assert [out(eng, i) for i in range(1, 4)] == [1, 99, 3]


def test_assumed_size_dummy_addresses_whole_actual():
    # an old-style assumed-size dummy (DIMENSION B(1)) reaches the whole actual array via
    # sequence association -- the actual's storage backs the dummy.
    src = (
        IH + "        DIMENSION A(5)\n        DATA A/10,20,30,40,50/\n"
        "        CALL SUMIT(A,5)\n"
        + END
        + "        SUBROUTINE SUMIT(B,N)\n        IMPLICIT INTEGER(A-Z)\n"
        "        COMMON /OUT/ V(40)\n        DIMENSION B(1)\n"
        "        IS=0\n        DO 1 I=1,N\n    1   IS=IS+B(I)\n        V(1)=IS\n" + END
    )
    eng = run(src)
    assert out(eng, 1) == 150
