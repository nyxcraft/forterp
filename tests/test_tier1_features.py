"""Tier-1 FORTRAN-10 V5 language features -- the parse-blockers that determine
source compatibility (any V5 source using them currently fails to load).

Implemented so far: BLOCK DATA (Ch16). Each test confirms source that uses the
construct now parses AND runs correctly.
"""

import pytest
from conftest import out, run

from forterp.dialect import F66, FORTRAN10
from forterp.fmt import unpack_chars


# ---- BLOCK DATA (V5 Ch16): declare-only unit that initializes labeled COMMON --
def test_block_data_initializes_common():
    # an (unnamed) BLOCK DATA unit seeds /CB/; the main program reads it
    src = (
        "        BLOCK DATA\n        IMPLICIT INTEGER(A-Z)\n"
        "        COMMON /CB/ K,M\n        DATA K,M /7,9/\n        END\n"
        "        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n"
        "        COMMON /OUT/ V(40)\n        COMMON /CB/ K,M\n"
        "        V(1)=K\n        V(2)=M\n        END\n"
    )
    eng = run(src)
    assert out(eng, 1) == 7
    assert out(eng, 2) == 9


def test_named_block_data_with_array():
    src = (
        "        BLOCK DATA INIT\n        IMPLICIT INTEGER(A-Z)\n"
        "        COMMON /TBL/ T(3)\n        DATA T /10,20,30/\n        END\n"
        "        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n"
        "        COMMON /OUT/ V(40)\n        COMMON /TBL/ T(3)\n"
        "        V(1)=T(1)\n        V(2)=T(2)\n        V(3)=T(3)\n        END\n"
    )
    eng = run(src)
    assert [out(eng, i) for i in range(1, 4)] == [10, 20, 30]


# ---- BLOCK DATA restrictions (§16.2) ---------------------------------------
def test_two_unnamed_block_data_rejected():
    # §16.2: "There must not be more than one unnamed block data subprogram." A second one would
    # silently overwrite the first ($BLOCKDATA collides), losing a block's init -- so it's a hard
    # error (all dialects).
    import forterp

    src = (
        "      BLOCK DATA\n      COMMON /A/ X\n      DATA X /1.0/\n      END\n"
        "      BLOCK DATA\n      COMMON /B/ Y\n      DATA Y /2.0/\n      END\n"
        "      PROGRAM T\n      COMMON /A/ X\n      COMMON /B/ Y\n      END\n"
    )
    with pytest.raises(forterp.ParseError, match="unnamed BLOCK DATA"):
        forterp.run_source(src, dialect=forterp.F77, target=forterp.NATIVE)


def test_one_unnamed_plus_named_block_data_both_run():
    # One unnamed + any number of NAMED block datas is fine -- each has its own name, no collision.
    import forterp

    src = (
        "      BLOCK DATA\n      COMMON /A/ X\n      DATA X /1.0/\n      END\n"
        "      BLOCK DATA INIT\n      COMMON /B/ Y\n      DATA Y /2.0/\n      END\n"
        "      PROGRAM T\n      COMMON /O/ Z(2)\n      COMMON /A/ X\n      COMMON /B/ Y\n"
        "      Z(1)=X\n      Z(2)=Y\n      END\n"
    )
    assert forterp.run_source(src, dialect=forterp.F77, target=forterp.NATIVE).commons["O"] == [
        1.0,
        2.0,
    ]


def test_partial_block_data_initializes_the_declared_prefix():
    # §16.2 "specify all entities" is NOT enforced (accept-more): a block data declaring only a
    # prefix of a common block initializes those entities correctly; the rest stay uninitialized.
    import forterp

    src = (
        "      BLOCK DATA\n      COMMON /CB/ A, B\n      DATA A, B /1.0, 2.0/\n      END\n"
        "      PROGRAM T\n      COMMON /O/ X(3)\n      COMMON /CB/ A, B, C\n"
        "      X(1)=A\n      X(2)=B\n      X(3)=C\n      END\n"
    )
    assert forterp.run_source(src, dialect=forterp.F77, target=forterp.NATIVE).commons["O"] == [
        1.0,
        2.0,
        0.0,
    ]


# ---- ENTRY (V5 15.7): alternate subprogram entry points --------------------
def test_entry_subroutine_alternate_entry():
    # CALL SECOND enters the subroutine at the ENTRY, binding the ENTRY's own dummy
    src = (
        "        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n        COMMON /OUT/ V(40)\n"
        "        CALL FIRST(10)\n        CALL SECOND(20)\n        END\n"
        "        SUBROUTINE FIRST(A)\n        IMPLICIT INTEGER(A-Z)\n"
        "        COMMON /OUT/ V(40)\n        V(1)=A\n        RETURN\n"
        "        ENTRY SECOND(B)\n        V(2)=B\n        RETURN\n        END\n"
    )
    eng = run(src)
    assert out(eng, 1) == 10  # CALL FIRST returned before reaching ENTRY SECOND
    assert out(eng, 2) == 20  # CALL SECOND entered at the ENTRY


def test_entry_function_returns_via_entry_name():
    src = (
        "        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n        COMMON /OUT/ V(40)\n"
        "        V(1)=TWICE(5)\n        V(2)=THRICE(5)\n        END\n"
        "        FUNCTION TWICE(N)\n        IMPLICIT INTEGER(A-Z)\n"
        "        TWICE=N*2\n        RETURN\n"
        "        ENTRY THRICE(N)\n        THRICE=N*3\n        RETURN\n        END\n"
    )
    eng = run(src)
    assert out(eng, 1) == 10
    assert out(eng, 2) == 15  # entered at THRICE; value returned via the entry name


def test_entry_fallthrough_is_noop():
    # normal execution flows THROUGH the ENTRY statement (it's nonexecutable)
    src = (
        "        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n        COMMON /OUT/ V(40)\n"
        "        CALL P1(7)\n        END\n"
        "        SUBROUTINE P1(A)\n        IMPLICIT INTEGER(A-Z)\n"
        "        COMMON /OUT/ V(40)\n        V(3)=A\n"
        "        ENTRY P2(A)\n        V(4)=A+1\n        RETURN\n        END\n"
    )
    eng = run(src)
    assert out(eng, 3) == 7  # P1 ran from the top
    assert out(eng, 4) == 8  # ... and fell THROUGH the ENTRY (no-op) to V(4)=A+1


# ---- ENCODE / DECODE (V5 10.15): internal formatted I/O to a buffer --------
def test_encode_renders_into_buffer():
    # ENCODE writes the formatted characters into the packed-ASCII buffer
    src = (
        "        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n        COMMON /OUT/ V(40)\n"
        "        DIMENSION BUF(4)\n"
        "        ENCODE(10,200,BUF) 42\n"
        "  200   FORMAT('N=',I3)\n"
        "        V(1)=BUF(1)\n        V(2)=BUF(2)\n        END\n"
    )
    eng = run(src)
    assert unpack_chars(out(eng, 1), 5) + unpack_chars(out(eng, 2), 5) == "N= 42     "


def test_encode_decode_roundtrip():
    # ENCODE values into a buffer, then DECODE them back
    src = (
        "        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n        COMMON /OUT/ V(40)\n"
        "        DIMENSION BUF(4)\n"
        "        ENCODE(20,100,BUF) 42,7\n"
        "        DECODE(20,100,BUF) I,J\n"
        "  100   FORMAT(I5,I5)\n"
        "        V(1)=I\n        V(2)=J\n        END\n"
    )
    eng = run(src)
    assert out(eng, 1) == 42
    assert out(eng, 2) == 7


# ---- NAMELIST (V5 Ch11): named I/O lists, $NAME ... $END records ------------
_NMLW = (
    "        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n        COMMON /OUT/ V(40)\n"
    "        NAMELIST /NL/ K,M\n        K=42\n        M=7\n"
    "        WRITE(6,NL)\n        END\n"
)


def test_namelist_write_output():
    txt = "".join(run(_NMLW).out)
    assert "$NL" in txt and "K= 42" in txt and "M= 7" in txt and "$END" in txt


def test_namelist_read_input():
    src = (
        "        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n        COMMON /OUT/ V(40)\n"
        "        NAMELIST /NL/ K,M\n        ACCEPT NL\n"
        "        V(1)=K\n        V(2)=M\n        END\n"
    )
    eng = run(src, inputs=[" $NL K=42, M=7 $"])
    assert out(eng, 1) == 42
    assert out(eng, 2) == 7


def test_namelist_read_array_with_repetition():
    # V5 11.2.1: a value list may use a repetition factor n*k
    src = (
        "        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n        COMMON /OUT/ V(40)\n"
        "        DIMENSION A(4)\n        NAMELIST /NL/ A\n        ACCEPT NL\n"
        "        V(1)=A(1)\n        V(2)=A(2)\n        V(3)=A(3)\n        V(4)=A(4)\n"
        "        END\n"
    )
    eng = run(src, inputs=[" $NL A=1, 3*9 $"])
    assert [out(eng, i) for i in range(1, 5)] == [1, 9, 9, 9]


def test_namelist_read_array_element_target():
    # V5 11.2.1: A(3)=val assigns the specific element, not the array start
    src = (
        "        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n        COMMON /OUT/ V(40)\n"
        "        DIMENSION A(4)\n        NAMELIST /NL/ A\n        ACCEPT NL\n"
        "        V(1)=A(1)\n        V(2)=A(2)\n        V(3)=A(3)\n        V(4)=A(4)\n"
        "        END\n"
    )
    eng = run(src, inputs=[" $NL A(3)=99 $"])
    assert [out(eng, i) for i in range(1, 5)] == [0, 0, 99, 0]


def _connect(unit, st):
    return lambda eng: eng.io.__setitem__(unit, st)


def test_namelist_write_to_file_unit():
    # WRITE(unit, NL) to a file ('w') unit stores the namelist as a text record,
    # NOT the terminal.
    src = (
        "        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n        COMMON /OUT/ V(40)\n"
        "        NAMELIST /NL/ K,M\n        K=42\n        M=7\n        WRITE(2,NL)\n"
        "        END\n"
    )
    eng = run(src, setup=_connect(2, {"mode": "w", "recs": [], "pos": 0}))
    rec = "".join(eng.io[2]["recs"])
    assert "$NL" in rec and "K= 42" in rec and "M= 7" in rec and "$END" in rec
    assert "".join(eng.out) == ""  # did not leak to the terminal


def test_namelist_read_from_file_unit():
    src = (
        "        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n        COMMON /OUT/ V(40)\n"
        "        NAMELIST /NL/ K,M\n        READ(2,NL)\n"
        "        V(1)=K\n        V(2)=M\n        END\n"
    )
    eng = run(src, setup=_connect(2, {"mode": "r", "recs": [" $NL K=11, M=22 $"], "pos": 0}))
    assert out(eng, 1) == 11 and out(eng, 2) == 22


# ---- random-access I/O (V5 10.3.5/10.14): READ/WRITE(u#r), FIND ------------
_RHEAD = "        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n        COMMON /OUT/ V(40)\n"
_REND = "        END\n"


def test_random_write_read_by_record_number():
    # write records out of order, then read them back by number (#r form)
    src = (
        _RHEAD + "        WRITE(1#3) 30\n        WRITE(1#1) 10\n"
        "        READ(1#1) A\n        READ(1#3) B\n"
        "        V(1)=A\n        V(2)=B\n" + _REND
    )
    eng = run(src)
    assert out(eng, 1) == 10
    assert out(eng, 2) == 30


def test_random_apostrophe_form():
    # the u'r record separator (lexes as a separator, not a string quote)
    src = _RHEAD + "        WRITE(1'2) 77\n        READ(1'2) A\n        V(1)=A\n" + _REND
    eng = run(src)
    assert out(eng, 1) == 77


def test_random_write_invalid_record_does_not_clobber():
    # WRITE(u'0) / negative REC must NOT corrupt an existing record. rec-1 was used as a
    # Python index, so REC=0 clobbered the last record (recs[-1]). An invalid record number
    # is an I/O error (no-op absent ERR=), never silent corruption.
    src = (
        _RHEAD + "        WRITE(1'3) 33\n        WRITE(1'0) 999\n"
        "        READ(1'3) K\n        V(1)=K\n" + _REND
    )
    assert out(run(src), 1) == 33  # record 3 intact (was 999 via the negative-index clobber)


def test_random_write_invalid_record_routes_to_err():
    # an invalid record number branches to ERR= (V5: it's an I/O error)
    src = (
        _RHEAD + "        WRITE(1'3) 33\n        WRITE(1'0,ERR=99) 999\n"
        "        K = 0\n        GO TO 100\n   99   K = -1\n  100   V(1)=K\n" + _REND
    )
    assert out(run(src), 1) == -1


def test_find_then_sequential_read():
    # FIND(u#r) positions the file; a following sequential READ(u) reads record r
    src = (
        _RHEAD + "        WRITE(1#1) 11\n        WRITE(1#2) 22\n"
        "        FIND(1#2)\n        READ(1) A\n        V(1)=A\n" + _REND
    )
    eng = run(src)
    assert out(eng, 1) == 22


def test_random_formatted_record_roundtrip():
    # a FORMAT on a random WRITE/READ renders/parses a TEXT record (V5 10.3.5)
    src = (
        _RHEAD + "        WRITE(1#2,10) 42\n        READ(1#2,10) K\n        V(1)=K\n"
        "  10    FORMAT(I5)\n" + _REND
    )
    eng = run(src)
    assert out(eng, 1) == 42
    assert isinstance(eng.io[1]["recs"][1], str)  # stored as a formatted text record


def test_define_file_random_unit_and_associated_variable():
    # DEFINE FILE sets up a random unit; the associated variable tracks the next record
    src = (
        _RHEAD + "        DEFINE FILE 8(100,5,U,NREC)\n        V(1)=NREC\n"
        "        WRITE(8#3) 77\n        V(2)=NREC\n"
        "        READ(8#3) M\n        V(3)=M\n        V(4)=NREC\n" + _REND
    )
    eng = run(src)
    assert out(eng, 1) == 1  # DEFINE FILE initializes NREC to 1
    assert out(eng, 2) == 4  # after WRITE record 3 -> next record 4
    assert out(eng, 3) == 77  # record read back
    assert out(eng, 4) == 4  # after READ record 3 -> next record 4


def test_open_associatevariable_tracks_next_record():
    src = (
        _RHEAD + "        OPEN(UNIT=4,ACCESS='RANDOM',ASSOCIATEVARIABLE=NXT)\n"
        "        V(1)=NXT\n        WRITE(4#7) 55\n        V(2)=NXT\n" + _REND
    )
    eng = run(src)
    assert out(eng, 1) == 1  # OPEN initializes NXT to 1
    assert out(eng, 2) == 8  # after WRITE record 7 -> next record 8


def test_binary_mode_record_is_genuine_forots_lscw():
    # OPEN MODE='BINARY' stores records in the real FOROTS LSCW word form (V5 D.5.2)
    from forterp.forbin import encode_record

    src = (
        _RHEAD + "        OPEN(UNIT=5,ACCESS='RANDOM',MODE='BINARY')\n"
        "        WRITE(5#1) 5,5,5\n" + _REND
    )
    eng = run(src)
    assert eng.io[5]["recs"][0] == encode_record([5, 5, 5])  # START + 3*5 + END


def test_binary_mode_roundtrips_int_and_real():
    src = (
        "        PROGRAM T\n        COMMON /OUT/ V(40)\n        REAL V\n"
        "        INTEGER J\n        REAL X\n"
        "        OPEN(UNIT=5,ACCESS='RANDOM',MODE='BINARY')\n"
        "        WRITE(5#1) 42\n        WRITE(5#2) 3.5\n"
        "        READ(5#1) J\n        READ(5#2) X\n"
        "        V(1)=J\n        V(2)=X\n        END\n"
    )
    eng = run(src)
    assert out(eng, 1) == 42  # integer round-trips (2's complement word)
    assert out(eng, 2) == 3.5  # real round-trips (DEC-10 float word)


# ---- EQUIVALENCE (V5 6.6): storage aliasing --------------------------------
_EHEAD = "        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n        COMMON /OUT/ V(40)\n"
_EEND = "        END\n"


def test_equivalence_same_type_alias():
    eng = run(_EHEAD + "        EQUIVALENCE (A,B)\n        A=42\n        V(1)=B\n" + _EEND)
    assert out(eng, 1) == 42  # A and B share one location


def test_equivalence_scalar_shares_array_element():
    eng = run(
        _EHEAD + "        DIMENSION Y(5)\n        EQUIVALENCE (X,Y(3))\n"
        "        Y(3)=77\n        V(1)=X\n        X=99\n        V(2)=Y(3)\n" + _EEND
    )
    assert out(eng, 1) == 77 and out(eng, 2) == 99  # X is Y(3)


def test_equivalence_is_transitive():
    eng = run(
        _EHEAD + "        EQUIVALENCE (A,B),(B,C)\n        A=5\n"
        "        V(1)=B\n        V(2)=C\n" + _EEND
    )
    assert out(eng, 1) == 5 and out(eng, 2) == 5


def test_equivalence_array_overlay():
    eng = run(
        _EHEAD + "        DIMENSION P(3),Q(3)\n        EQUIVALENCE (P(1),Q(1))\n"
        "        P(2)=22\n        V(1)=Q(2)\n" + _EEND
    )
    assert out(eng, 1) == 22  # P and Q overlap element-for-element


def test_equivalence_complex_scalar_over_real_pair():
    # A COMPLEX scalar EQUIVALENCEd onto a REAL(2) array occupies two words: R(1) is the real
    # part, R(2) the imaginary (X3.9-1978 storage association). The whole FCVS COMPLEX cluster
    # (FM809 et al.) leans on this idiom. Storage is genuinely shared both ways.
    eng = run(
        "        PROGRAM T\n        COMMON /OUT/ ARE, AIM, BACK\n"
        "        COMPLEX C\n        REAL R(2)\n        EQUIVALENCE (C, R)\n"
        "        C = (3.5, -2.25)\n"
        "        ARE = R(1)\n        AIM = R(2)\n"  # read the parts out through the REAL overlay
        "        R(1) = 8.0\n        R(2) = 9.0\n"  # write through the overlay ...
        "        BACK = REAL(C) + AIMAG(C)\n        END\n"  # ... and the COMPLEX sees it
    )
    assert eng.commons["OUT"][:3] == [3.5, -2.25, 17.0]


def test_equivalence_extends_common_forward():
    # the manual's example: COMMON/R/X,Y,Z + EQUIVALENCE(A,Y) -> A(1)=Y, A(2)=Z, A(3),A(4)
    eng = run(
        _EHEAD + "        COMMON /R/ X,Y,Z\n        DIMENSION A(4)\n"
        "        EQUIVALENCE (A,Y)\n        Y=10\n        Z=20\n        A(3)=30\n"
        "        V(1)=A(1)\n        V(2)=A(2)\n        V(3)=A(3)\n" + _EEND
    )
    assert [out(eng, i) for i in range(1, 4)] == [10, 20, 30]


def test_equivalence_data_initialization():
    eng = run(
        _EHEAD + "        DIMENSION Y(3)\n        EQUIVALENCE (X,Y(1))\n"
        "        DATA Y(1)/55/\n        V(1)=X\n" + _EEND
    )
    assert out(eng, 1) == 55  # DATA on Y(1) is visible through X


# ---- illegal EQUIVALENCE shapes: rejected, not silently mis-laid (R4-b) ----
# All three are non-conforming in ANSI F66 itself (10.2.1 / 10.2.2 / contradictory), so the
# diagnostic is ungated -- F66 and FORTRAN10 both raise rather than pick a wrong layout. The
# programs are plain ANSI (no IMPLICIT) so the error under F66 is the EQUIVALENCE, not a gate.
@pytest.mark.parametrize("dlc", [F66, FORTRAN10])
def test_equivalence_backward_common_extension_rejected(dlc):
    # EQUIVALENCE(A(3),X), X first in /CB/: would extend the block backward (F66 10.2.2).
    # Old behavior silently clamped A's base to 0, aliasing A(3) to Z instead of X.
    src = (
        "        PROGRAM T\n        COMMON /CB/ X,Y,Z\n        DIMENSION A(4)\n"
        "        EQUIVALENCE (A(3),X)\n        END\n"
    )
    with pytest.raises(RuntimeError, match="backward"):
        run(src, dialect=dlc)


@pytest.mark.parametrize("dlc", [F66, FORTRAN10])
def test_equivalence_contradictory_rejected(dlc):
    # A can't share storage with both C(1) and C(2). Old behavior dropped the 2nd silently.
    src = (
        "        PROGRAM T\n        DIMENSION C(3)\n"
        "        EQUIVALENCE (A,C(1)),(A,C(2))\n        END\n"
    )
    with pytest.raises(RuntimeError, match="contradictory"):
        run(src, dialect=dlc)


@pytest.mark.parametrize("dlc", [F66, FORTRAN10])
def test_equivalence_across_two_common_blocks_rejected(dlc):
    # P in /A/, Q in /B/: can't associate two COMMON blocks (F66 10.2.1). Old behavior bound
    # Q into /A/ and orphaned /B/'s slot.
    src = (
        "        PROGRAM T\n        COMMON /A/ P\n        COMMON /B/ Q\n"
        "        EQUIVALENCE (P,Q)\n        END\n"
    )
    with pytest.raises(RuntimeError, match="two COMMON blocks"):
        run(src, dialect=dlc)


def test_equivalence_character_with_numeric_rejected():
    # §8.2.3: a CHARACTER entity may be equivalenced only with other CHARACTER entities. Mixing
    # char and numeric (its only use is byte type-punning, which the value-slot model can't do)
    # is a hard error on every dialect. (CHARACTER needs the F77 dialect.)
    import forterp

    src = (
        "      PROGRAM T\n      REAL R\n      CHARACTER*4 C\n      EQUIVALENCE (R, C)\n      END\n"
    )
    with pytest.raises(RuntimeError, match="CHARACTER entity"):
        forterp.run_source(src, dialect=forterp.F77, target=forterp.NATIVE)


def test_equivalence_character_with_character_is_allowed():
    import forterp

    src = (
        "      PROGRAM T\n      COMMON /O/ S\n      CHARACTER*4 S, A, B\n"
        "      EQUIVALENCE (A, B)\n      A='WXYZ'\n      S=B\n      END\n"
    )
    assert forterp.run_source(src, dialect=forterp.F77, target=forterp.NATIVE).commons["O"][0] == (
        "WXYZ"
    )
