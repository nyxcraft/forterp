"""Word-addressable typed memory (the punning substrate, P1). Every expected word here is the
genuine KL10 bit pattern captured from a real PDP-10 under DEC FORTRAN-10 (SIMH KS10) -- see
~/f66spec/notes/PDP10-PUNNING-PROBE*.OUT. The codec must reproduce those bits and must reinterpret
across types the way the real machine does."""

import forterp
from forterp.forbin import double_to_dec10, double_to_dec10_pair
from forterp.target import PDP10
from forterp.wordmem import Pdp10WordMemory, units

M = Pdp10WordMemory(PDP10)


def _run(src, out_type):
    """Run a punning snippet on PDP10 with word_memory ON; decode /O/ by the given type."""
    eng = forterp.run_source(src, dialect=forterp.F66, target=forterp.PDP10, word_memory=True)
    return eng.wmem.read(eng.commons["O"], 0, out_type)


def test_storage_units():
    assert units("INTEGER") == 1 and units("REAL") == 1 and units("LOGICAL") == 1
    assert units("DOUBLE PRECISION") == 2 and units("COMPLEX") == 2


def test_single_real_word_matches_kl10():
    # REAL -> 36-bit word, bit-exact vs the KL10 (PROBE1)
    cases = {
        1.0: 0o201400000000,
        1.5: 0o201600000000,
        0.5: 0o200400000000,
        3.14: 0o202621727024,
        -2.0: 0o575400000000,
        100.0: 0o207620000000,
    }
    for v, word in cases.items():
        s = [0]
        M.write(s, 0, "REAL", v)
        assert s[0] == word, (v, oct(s[0]), oct(word))  # bit-exact vs the KL10
    # round-trip is exact for values representable in single precision; 3.14 reads back as the
    # faithful single approximation (3.1399999...), exactly as the real machine would.
    for v in (1.0, 1.5, 0.5, -2.0, 100.0):
        s = [0]
        M.write(s, 0, "REAL", v)
        assert M.read(s, 0, "REAL") == v
    s = [0]
    M.write(s, 0, "REAL", 3.14)
    assert abs(M.read(s, 0, "REAL") - 3.14) < 1e-6


def test_real_punned_as_integer_is_the_machine_word():
    # write a REAL, read it back as INTEGER -> the genuine word bits (the classic float-bits idiom)
    s = [0]
    M.write(s, 0, "REAL", 1.5)
    assert M.read(s, 0, "INTEGER") == 0o201600000000  # positive word, reads as itself


def test_integer_word_punned_as_real_reinterprets():
    # the reverse direction (PROBE2 (A)): a known word read as REAL decodes to the value
    s = [0o201600000000]
    assert M.read(s, 0, "REAL") == 1.5
    s = [0o575400000000]  # the KL10 word for -2.0
    assert M.read(s, 0, "REAL") == -2.0


def test_double_words_match_kl10_and_round_trip():
    # DOUBLE -> two words (PROBE1); 1.5 is exact, -3.14 exercises the low-word sign-bit clear
    s = [0, 0]
    M.write(s, 0, "DOUBLE PRECISION", 1.5)
    assert (s[0], s[1]) == (0o201600000000, 0)
    M.write(s, 0, "DOUBLE PRECISION", -3.14)
    assert s[0] == 0o575156050753 and s[1] >> 35 == 0  # hi exact, low-word sign bit cleared
    assert M.read(s, 0, "DOUBLE PRECISION") == -3.14


def test_double_punned_as_two_integers_is_the_doubleword():
    # a DOUBLE's two words read as INTEGERs are the genuine machine words (faithful idiom)
    s = [0, 0]
    M.write(s, 0, "DOUBLE PRECISION", 1.0)
    assert M.read(s, 0, "INTEGER") == 0o201400000000
    assert M.read(s, 1, "INTEGER") == 0


def test_double_high_word_punned_as_single_real():
    # a DOUBLE's high word read back as a single REAL ~= the value (confirmed on real hardware)
    s = [0, 0]
    M.write(s, 0, "DOUBLE PRECISION", 1.5)
    assert M.read(s, 0, "REAL") == 1.5


def test_complex_splits_into_two_single_words():
    s = [0, 0]
    M.write(s, 0, "COMPLEX", complex(1.5, 3.14))
    assert M.read(s, 0, "REAL") == 1.5  # real part word as a single
    assert s[0] == 0o201600000000  # ... and it's the genuine 1.5 word
    assert M.read(s, 0, "COMPLEX") == complex(1.5, M.read(s, 1, "REAL"))


def test_logical_word():
    s = [0]
    M.write(s, 0, "LOGICAL", PDP10.from_bool(True))  # .TRUE. == -1 on PDP10
    assert M.read(s, 0, "LOGICAL") == -1
    assert M.read(s, 0, "INTEGER") == -1  # all-bits-set word


# ---- engine integration: the word_memory flag makes all four punning directions faithful -------
# (PDP10 only; default OFF -- the rest of the suite runs with it off and is unaffected.)


def test_word_memory_real_punned_as_integer():
    # set a REAL, read the aliased INTEGER -> the genuine KL10 machine word (was the float value)
    src = (
        "      PROGRAM T\n      COMMON /O/ N\n      INTEGER N\n"
        "      REAL X\n      INTEGER K\n      EQUIVALENCE (X,K)\n"
        "      X=1.5\n      N=K\n      END\n"
    )
    assert _run(src, "INTEGER") == double_to_dec10(1.5) == 0o201600000000


def test_word_memory_integer_punned_as_real():
    # set an INTEGER bit pattern, read the aliased REAL -> the decoded value (was the int as float)
    w = double_to_dec10(1.5)
    src = (
        f"      PROGRAM T\n      COMMON /O/ Y\n      REAL Y\n"
        f"      INTEGER K\n      REAL X\n      EQUIVALENCE (K,X)\n"
        f"      K={w}\n      Y=X\n      END\n"
    )
    assert _run(src, "REAL") == 1.5


def test_word_memory_double_punned_as_real():
    # the previously-broken direction: a DOUBLE's high word read as a single REAL -> the value
    src = (
        "      PROGRAM T\n      COMMON /O/ Y\n      REAL Y\n"
        "      DOUBLE PRECISION D\n      REAL X\n      EQUIVALENCE (D,X)\n"
        "      D=1.5D0\n      Y=X\n      END\n"
    )
    assert _run(src, "REAL") == 1.5


def test_word_memory_normal_double_arithmetic_round_trips():
    # a NON-punning program still computes correctly under word_memory (decode/encode round-trip)
    src = (
        "      PROGRAM T\n      COMMON /O/ OUT\n      DOUBLE PRECISION OUT,X\n"
        "      X=2.5D0\n      OUT=X*2.0D0\n      END\n"
    )
    assert _run(src, "DOUBLE PRECISION") == 5.0


def test_word_memory_off_by_default():
    # default OFF: a storage-associated REAL/INTEGER alias reads the typed value, not the word
    eng = forterp.run_source(
        "      PROGRAM T\n      COMMON /O/ N\n      INTEGER N\n"
        "      REAL X\n      INTEGER K\n      EQUIVALENCE (X,K)\n"
        "      X=1.5\n      N=K\n      END\n",
        dialect=forterp.F66,
        target=forterp.PDP10,
    )
    assert eng.word_memory is False  # not enabled unless asked


# ---- word_memory step 3a: single-word array elements pun faithfully -----------------------------


def test_word_memory_real_array_punned_as_integer():
    # a REAL array element written, read through an aliased INTEGER array -> the machine word
    src = (
        "      PROGRAM T\n      COMMON /O/ N\n      INTEGER N\n"
        "      REAL A(3)\n      INTEGER B(3)\n      EQUIVALENCE (A,B)\n"
        "      A(2)=1.5\n      N=B(2)\n      END\n"
    )
    assert _run(src, "INTEGER") == double_to_dec10(1.5)


def test_word_memory_real_array_arithmetic_round_trips():
    # a non-punning REAL array program still computes correctly under word_memory
    src = (
        "      PROGRAM T\n      COMMON /O/ OUT\n      REAL OUT,A(3)\n"
        "      A(1)=2.0\n      A(2)=3.0\n      A(3)=A(1)+A(2)\n      OUT=A(3)\n      END\n"
    )
    assert _run(src, "REAL") == 5.0


def test_word_memory_double_array_two_words_per_element():
    # step 3b: a DOUBLE array reserves two words/element, so it round-trips AND a following COMMON
    # member sits at the word-accurate offset (3 doubles -> word 6).
    src = (
        "      PROGRAM T\n      COMMON /CB/ D(3), K\n      DOUBLE PRECISION D\n      INTEGER K\n"
        "      D(1)=1.5D0\n      D(2)=2.5D0\n      D(3)=D(1)+D(2)\n      K=7\n      END\n"
    )
    eng = forterp.run_source(src, dialect=forterp.F66, target=forterp.PDP10, word_memory=True)
    st = eng.commons["CB"]
    assert len(st) == 7  # 3 doubles * 2 words + 1 integer
    assert eng.wmem.read(st, 4, "DOUBLE PRECISION") == 4.0  # D(3) at word 2*2=4
    assert eng.wmem.read(st, 6, "INTEGER") == 7  # K lands at word 6, not 3


def test_word_memory_double_array_punned_as_integer_words():
    # a DOUBLE array element's two words read through an aliased INTEGER array are the doubleword
    src = (
        "      PROGRAM T\n      COMMON /O/ N\n      INTEGER N\n"
        "      DOUBLE PRECISION D(2)\n      INTEGER W(4)\n      EQUIVALENCE (D,W)\n"
        "      D(1)=1.5D0\n      N=W(1)\n      END\n"
    )
    assert _run(src, "INTEGER") == double_to_dec10_pair(1.5)[0]


# ---- word_memory step 4: I/O and argument passing of word-backed entities ----------------------


def test_word_memory_io_writes_decoded_value():
    # WRITE of a storage-associated REAL formats the decoded value, not the raw word
    eng = forterp.run_source(
        "      PROGRAM T\n      COMMON /C/ X\n      REAL X\n"
        "      X=1.5\n      WRITE(6,100)X\n100   FORMAT(1X,F8.4)\n      END\n",
        dialect=forterp.F66,
        target=forterp.PDP10,
        word_memory=True,
    )
    assert eng.out == ["  1.5000\n"]


def test_word_memory_arg_pass_scalar():
    # a COMMON scalar passed by reference is modified through the WordRef (decode/encode)
    src = (
        "      PROGRAM T\n      COMMON /C/ X, OUT\n      REAL X, OUT\n"
        "      X=3.0\n      CALL DBL(X)\n      OUT=X\n      END\n"
        "      SUBROUTINE DBL(A)\n      A=A*2.0\n      RETURN\n      END\n"
    )
    eng = forterp.run_source(src, dialect=forterp.F66, target=forterp.PDP10, word_memory=True)
    assert eng.wmem.read(eng.commons["C"], 1, "REAL") == 6.0


def test_word_memory_arg_pass_whole_array():
    src = (
        "      PROGRAM T\n      COMMON /C/ A(3), OUT\n      REAL A, OUT\n"
        "      A(1)=4.0\n      CALL FIRST(A)\n      OUT=A(1)\n      END\n"
        "      SUBROUTINE FIRST(V)\n      DIMENSION V(3)\n"
        "      V(1)=V(1)+1.0\n      RETURN\n      END\n"
    )
    eng = forterp.run_source(src, dialect=forterp.F66, target=forterp.PDP10, word_memory=True)
    assert eng.wmem.read(eng.commons["C"], 3, "REAL") == 5.0


def test_word_memory_arg_pass_array_element_seq_association():
    # passing A(2) to an array dummy: the dummy's element 0 IS A(2) (sequence association)
    src = (
        "      PROGRAM T\n      COMMON /C/ A(5), OUT\n      REAL A, OUT\n"
        "      A(2)=4.0\n      CALL FIRST(A(2))\n      OUT=A(2)\n      END\n"
        "      SUBROUTINE FIRST(V)\n      DIMENSION V(3)\n"
        "      V(1)=V(1)+1.0\n      RETURN\n      END\n"
    )
    eng = forterp.run_source(src, dialect=forterp.F66, target=forterp.PDP10, word_memory=True)
    assert eng.wmem.read(eng.commons["C"], 5, "REAL") == 5.0


# ---- LP64 little-endian / IEEE codec (P2) -------------------------------------------------------
# Every expected value here is the genuine gfortran-on-x86_64 bit pattern (validated in the PoC,
# ~/f66spec scratch; identical across all gfortran --std modes -- it's IEEE layout, not language).

from forterp.wordmem import Lp64LeByteMemory  # noqa: E402

L = Lp64LeByteMemory()


def test_lp64_units_in_bytes():
    assert L.units("REAL") == 4 and L.units("INTEGER") == 4 and L.units("LOGICAL") == 4
    assert L.units("DOUBLE PRECISION") == 8 and L.units("COMPLEX") == 8


def test_lp64_real_punned_as_integer_matches_gfortran():
    b = L.alloc(4)
    L.write(b, 0, "REAL", 3.14)
    assert L.read(b, 0, "INTEGER") == 0x4048F5C3  # gfortran: 1078523331


def test_lp64_integer_punned_as_real():
    b = L.alloc(4)
    L.write(b, 0, "INTEGER", 0x4048F5C3)
    assert abs(L.read(b, 0, "REAL") - 3.14) < 1e-6


def test_lp64_double_punned_as_two_integer_words_matches_gfortran():
    b = L.alloc(8)
    L.write(b, 0, "DOUBLE PRECISION", 1.5)
    assert L.read(b, 0, "INTEGER") == 0  # low word
    assert L.read(b, 4, "INTEGER") == 0x3FF80000  # high word; gfortran: 1073217536


def test_lp64_two_integer_words_punned_as_double():
    b = L.alloc(8)
    L.write(b, 0, "INTEGER", 0)
    L.write(b, 4, "INTEGER", 0x40000000)
    assert L.read(b, 0, "DOUBLE PRECISION") == 2.0


def test_lp64_double_round_trips_exactly():
    b = L.alloc(8)
    L.write(b, 0, "DOUBLE PRECISION", 3.141592653589793)
    assert L.read(b, 0, "DOUBLE PRECISION") == 3.141592653589793


def test_lp64_complex_two_singles():
    b = L.alloc(8)
    L.write(b, 0, "COMPLEX", complex(1.5, 2.0))
    assert L.read(b, 0, "REAL") == 1.5 and L.read(b, 4, "REAL") == 2.0
    assert L.read(b, 0, "COMPLEX") == complex(1.5, 2.0)


def test_lp64_negative_integer_wraps_signed_32():
    b = L.alloc(4)
    L.write(b, 0, "INTEGER", -2)
    assert L.read(b, 0, "INTEGER") == -2


# ---- LP64LE through the engine: faithful punning on the 64-bit IEEE target (P2 step 2) ----------


def _run_lp64(src, out_type, off=0):
    from forterp.target import LP64LE

    eng = forterp.run_source(src, dialect=forterp.F77, target=LP64LE, word_memory=True)
    return eng.wmem.read(eng.commons["O"], off, out_type)


def test_lp64_engine_real_punned_as_integer_matches_gfortran():
    src = (
        "      PROGRAM T\n      COMMON /O/ N\n      INTEGER N\n"
        "      REAL X\n      INTEGER K\n      EQUIVALENCE (X,K)\n"
        "      X=3.14\n      N=K\n      END\n"
    )
    assert _run_lp64(src, "INTEGER") == 0x4048F5C3  # gfortran x86_64


def test_lp64_engine_double_arithmetic_round_trips():
    src = (
        "      PROGRAM T\n      COMMON /O/ OUT\n      DOUBLE PRECISION OUT,X\n"
        "      X=2.5D0\n      OUT=X*2.0D0\n      END\n"
    )
    assert _run_lp64(src, "DOUBLE PRECISION") == 5.0


def test_lp64_engine_block_layout_is_byte_accurate():
    # REAL X, INTEGER K, INTEGER OUT -> 12 bytes; K at byte 4, OUT at byte 8
    from forterp.target import LP64LE

    src = (
        "      PROGRAM T\n      COMMON /O/ X, K, M\n      REAL X\n      INTEGER K, M\n"
        "      X=1.0\n      K=99\n      M=K\n      END\n"
    )
    eng = forterp.run_source(src, dialect=forterp.F77, target=LP64LE, word_memory=True)
    assert len(eng.commons["O"]) == 12
    assert eng.wmem.read(eng.commons["O"], 4, "INTEGER") == 99  # K at byte 4
    assert eng.wmem.read(eng.commons["O"], 8, "INTEGER") == 99  # M = K, at byte 8


# ---- VAX codec: LE integers, middle-endian F/D floats (best effort, UNVALIDATED) ----------------
# No VAX oracle yet; these pin the documented format, anchored by the canonical F_float 1.0=0x4080
# and self-consistent round-trips. Correct against a real VAX/simulator when one exists.

from forterp.wordmem import VaxByteMemory  # noqa: E402

VX = VaxByteMemory()


def _le32(b):
    return b[0] | b[1] << 8 | b[2] << 16 | b[3] << 24


def test_vax_f_float_matches_documented_patterns():
    cases = {1.0: 0x00004080, 0.5: 0x00004000, 2.0: 0x00004100, 3.0: 0x00004140, -1.0: 0x0000C080}
    for v, word in cases.items():
        b = VX.alloc(4)
        VX.write(b, 0, "REAL", v)
        assert _le32(b) == word, (v, hex(_le32(b)), hex(word))
        assert VX.read(b, 0, "REAL") == v  # round-trips


def test_vax_real_punned_as_integer_is_word_swapped_float():
    b = VX.alloc(4)
    VX.write(b, 0, "REAL", 1.0)
    assert VX.read(b, 0, "INTEGER") == 0x4080  # F_float 1.0, words swapped -> 0x00004080


def test_vax_d_float_round_trips():
    for v in (1.0, 0.5, 3.14, -2.5, 1234.5):
        b = VX.alloc(8)
        VX.write(b, 0, "DOUBLE PRECISION", v)
        assert abs(VX.read(b, 0, "DOUBLE PRECISION") - v) <= 1e-12 * max(1.0, abs(v))


def test_vax_integer_is_plain_little_endian():
    b = VX.alloc(4)
    VX.write(b, 0, "INTEGER", 0x04030201)
    assert list(b) == [0x01, 0x02, 0x03, 0x04]  # LE
    VX.write(b, 0, "INTEGER", -2)
    assert VX.read(b, 0, "INTEGER") == -2


def test_vax_engine_punning_and_layout():
    import forterp
    from forterp.target import VAX

    src = (
        "      PROGRAM T\n      COMMON /O/ X, K, M\n      REAL X\n      INTEGER K, M\n"
        "      X=1.0\n      K=42\n      M=K\n      END\n"
    )
    eng = forterp.run_source(src, dialect=forterp.F77, target=VAX, word_memory=True)
    assert len(eng.commons["O"]) == 12  # REAL(4) + INTEGER(4) + INTEGER(4), byte-addressed
    assert eng.wmem.read(eng.commons["O"], 4, "INTEGER") == 42  # K at byte 4
