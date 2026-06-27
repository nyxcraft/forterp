"""Word-addressable typed memory (the punning substrate, P1). Every expected word here is the
genuine KL10 bit pattern captured from a real PDP-10 under DEC FORTRAN-10 (SIMH KS10) -- see
~/f66spec/notes/PDP10-PUNNING-PROBE*.OUT. The codec must reproduce those bits and must reinterpret
across types the way the real machine does."""

import forterp
from forterp.forbin import double_to_dec10
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
