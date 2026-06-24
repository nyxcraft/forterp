"""FOROTS binary record codec (forbin.py) -- validated against the FORTRAN-10
V5 manual, Appendix D.5.2 (the LSCW format and its D-6 worked example).
"""

import math

import pytest

from forterp.forbin import (
    Dec10FloatError,
    dec10_pair_to_double,
    dec10_to_double,
    decode_binary_file,
    decode_record,
    decode_sequential,
    double_to_dec10,
    double_to_dec10_pair,
    encode_binary_file,
    encode_record,
    encode_sequential,
    pack_core_dump,
    unpack_core_dump,
)


# ---- the manual's D-6 worked example (GROUND TRUTH) ------------------------
def test_lscw_matches_manual_example():
    # WRITE(1'1) (I, J=1,100) with I=5 -> START, 100 data words (=5), END
    rec = encode_record([5] * 100)
    assert rec[0] == 0o001000000145  # START: code 001, count 0o145 = 101
    assert rec[-1] == 0o003000000146  # END:   code 003, count 0o146 = 102
    assert rec[1:-1] == [5] * 100  # the 100 data words
    assert len(rec) == 102  # START + 100 + END


def test_lscw_count_fields():
    # START count = words following it through END; END count = total incl. LSCWs
    rec = encode_record([0] * 3)
    assert (rec[0] >> 27) == 0o1 and (rec[0] & ((1 << 27) - 1)) == 4  # 3 data + END
    assert (rec[-1] >> 27) == 0o3 and (rec[-1] & ((1 << 27) - 1)) == 5  # 3+2 total


def test_decode_round_trips_framing():
    data = [11, 22, 33, 44]
    rec = encode_record(data)
    got, nxt = decode_record(rec, 0)
    assert got == data and nxt == len(rec)


def test_decode_two_consecutive_records():
    words = encode_record([5] * 100) + encode_record([7] * 100)
    d1, p1 = decode_record(words, 0)
    d2, p2 = decode_record(words, p1)
    assert d1 == [5] * 100 and d2 == [7] * 100 and p2 == len(words)


# ---- sequential framing: the manual's D-7/D-8 two-record example (GROUND TRUTH) ----
def test_sequential_matches_manual_continue_example():
    # Manual D.5.2 p.D-8: WRITE(1)(I,J=1,100) then WRITE(1)(J,K=1,100). Record 1 (102
    # words) fits in block 0; record 2 starts at word 0o146 and crosses the 0o200 boundary.
    words = encode_sequential([[5] * 100, [7] * 100])
    assert words[0] == 0o001000000145  # rec1 START: count 0o145 = 101
    assert words[0o145] == 0o003000000146  # rec1 END: total 0o146 = 102
    assert words[0o146] == 0o001000000032  # rec2 START at 0o146: count 0o32 = 26 (to boundary)
    assert words[0o200] == 0o002000000114  # CONTINUE at 0o200 boundary: count 0o114 = 76
    assert (words[0o200 + 0o114] >> 27) == 0o3  # END follows the 76-word continuation segment


def test_sequential_round_trips_multiblock_records():
    recs = [list(range(300)), [42] * 2574, [1, 2, 3], list(range(1, 130))]  # D- and MAPS-sized
    assert decode_sequential(encode_sequential(recs)) == recs


def test_sequential_short_record_has_no_continue():
    words = encode_sequential([[9] * 10])  # 12 words << 128: START + data + END only
    assert [w >> 27 for w in words] == [0o1] + [0] * 10 + [0o3]


# ---- core-dump byte packing -------------------------------------------------
def test_core_dump_known_vector():
    # the START LSCW 0o001000000145 -> 5 left-justified bytes
    assert pack_core_dump([0o001000000145]) == bytes((0x00, 0x80, 0x00, 0x06, 0x50))


def test_core_dump_round_trips_full_width():
    words = [0, 1, (1 << 36) - 1, 0o001000000145, 0o525252525252, 0o252525252525]
    assert unpack_core_dump(pack_core_dump(words)) == words


def test_core_dump_rejects_misaligned_bytes():
    import pytest

    with pytest.raises(ValueError):
        unpack_core_dump(b"\x00\x01\x02")  # not a multiple of 5


def test_binary_file_round_trips_records():
    recs = [list(range(300)), [7] * 2574, [0o777777777777, 0]]
    assert decode_binary_file(encode_binary_file(recs)) == recs


# ---- engine: dec_files writes/reads REAL FOROTS binary files (opt-in) ----------
def test_dec_files_engine_writes_real_binary_and_round_trips(tmp_path):
    import forterp

    src = """      PROGRAM T
      COMMON /OUT/ MB(5), II, JJ, KK
      INTEGER MA(5)
      DATA MA /10,20,30,40,50/
      OPEN(UNIT=1,FILE='T.DAT',ACCESS='SEQOUT')
      WRITE(1) MA
      WRITE(1) 7, 8, 9
      CLOSE(UNIT=1)
      OPEN(UNIT=1,FILE='T.DAT',ACCESS='SEQIN')
      READ(1) MB
      READ(1) II, JJ, KK
      CLOSE(UNIT=1)
      END
"""
    eng = forterp.run_source(
        src, dialect=forterp.FORTRAN10, target=forterp.PDP10, root=str(tmp_path), dec_files=True
    )
    out = eng.commons["OUT"]
    assert out[:5] == [10, 20, 30, 40, 50] and out[5:8] == [7, 8, 9]  # round-tripped through disk
    raw = (tmp_path / "T.DAT").read_bytes()
    assert raw[:1] == b"\x00"  # a real FOROTS file (core-dump START LSCW), not JSON's b"["
    assert decode_binary_file(raw) == [[10, 20, 30, 40, 50], [7, 8, 9]]  # external readers agree


# ---- DECsystem-10 single-precision floating point --------------------------
def test_dec10_one_is_documented_constant():
    assert double_to_dec10(1.0) == 0o201400000000  # the canonical PDP-10 1.0


def test_dec10_zero():
    assert double_to_dec10(0.0) == 0
    assert dec10_to_double(0) == 0.0


def test_dec10_float_round_trip():
    # DEC-10 single has a 27-bit fraction (~8 decimal digits); use a matching tol
    for x in (1.0, -1.0, 0.5, -0.25, 3.1415927, -2.5, 100.0, 1.0e8, 1.0e-8):
        back = dec10_to_double(double_to_dec10(x))
        assert math.isclose(back, x, rel_tol=1e-7), (x, back)


def test_dec10_negative_is_twos_complement_of_positive():
    pos = double_to_dec10(2.5)
    neg = double_to_dec10(-2.5)
    assert neg == ((-pos) & ((1 << 36) - 1))


# ---- R3 #3: unrepresentable floats raise, not silently wrap / crash ---------
@pytest.mark.parametrize("x", [float("inf"), float("-inf"), float("nan")])
def test_dec10_rejects_inf_and_nan(x):
    # was a bare OverflowError/ValueError leaking out of the codec
    with pytest.raises(Dec10FloatError):
        double_to_dec10(x)


@pytest.mark.parametrize("x", [1.0e40, -1.0e40, 1.0e-50])
def test_dec10_rejects_out_of_range_magnitude(x):
    # exponent outside the 8-bit excess-128 field: was silently wrapped (corruption)
    with pytest.raises(Dec10FloatError):
        double_to_dec10(x)


def test_dec10_in_range_extremes_still_encode():
    # just inside the representable range (|exponent| ~ 127) still round-trips
    for x in (1.0e37, 1.0e-37):
        assert math.isclose(dec10_to_double(double_to_dec10(x)), x, rel_tol=1e-6)


# ---- DECsystem-10 double-precision floating point (two-word KL10 format) ----
def test_dec10_double_one_is_single_high_word_plus_zero_low():
    # the high word equals the single-precision 1.0; the low word is 0
    assert double_to_dec10_pair(1.0) == (0o201400000000, 0)


def test_dec10_double_zero():
    assert double_to_dec10_pair(0.0) == (0, 0)
    assert dec10_pair_to_double(0, 0) == 0.0


def test_dec10_double_round_trips_a_python_float_exactly():
    # 62 fraction bits hold a 53-bit Python double with no loss -> exact equality, not isclose
    for x in (0.1, -0.1, 3.141592653589793, 1.0 / 3.0, -2.5, 1.0e10 + 0.5, 1.0e-9, 123456.789):
        assert dec10_pair_to_double(*double_to_dec10_pair(x)) == x, x


def test_dec10_double_keeps_precision_a_single_would_lose():
    # the whole point of two words: 0.1 survives the double round-trip but not the single one
    assert dec10_pair_to_double(*double_to_dec10_pair(0.1)) == 0.1
    assert dec10_to_double(double_to_dec10(0.1)) != 0.1


def test_dec10_double_negative_is_twos_complement_of_the_doubleword():
    hi_p, lo_p = double_to_dec10_pair(2.5)
    hi_n, lo_n = double_to_dec10_pair(-2.5)
    pos = (hi_p << 36) | lo_p
    neg = (hi_n << 36) | lo_n
    assert neg == ((-pos) & ((1 << 72) - 1))


@pytest.mark.parametrize("x", [float("inf"), float("-inf"), float("nan"), 1.0e40, 1.0e-50])
def test_dec10_double_rejects_unrepresentable(x):
    with pytest.raises(Dec10FloatError):
        double_to_dec10_pair(x)


def test_dec_files_double_precision_round_trips_as_two_words(tmp_path):
    import forterp

    src = """      PROGRAM T
      COMMON /OUT/ E(3)
      DOUBLE PRECISION D(3), E
      DATA D /0.1D0, 3.141592653589793D0, -2.5D0/
      OPEN(UNIT=1,FILE='D.DAT',ACCESS='SEQOUT')
      WRITE(1) D
      CLOSE(UNIT=1)
      OPEN(UNIT=1,FILE='D.DAT',ACCESS='SEQIN')
      READ(1) E
      CLOSE(UNIT=1)
      END
"""
    eng = forterp.run_source(
        src, dialect=forterp.FORTRAN10, target=forterp.PDP10, root=str(tmp_path), dec_files=True
    )
    e = eng.commons["OUT"]
    assert e[0] == 0.1 and e[2] == -2.5  # exact (62-bit) round-trip, not 27-bit truncation
    assert math.isclose(e[1], 3.141592653589793, rel_tol=1e-15)
    rec = decode_binary_file((tmp_path / "D.DAT").read_bytes())
    assert len(rec) == 1 and len(rec[0]) == 6  # 3 doubles -> SIX words (two each), not three


def test_open_binary_file_without_dec_files_errors_instead_of_silent_text(tmp_path):
    import forterp

    # a real FOROTS binary file opened on a unit that isn't in dec_files mode used to be read
    # as garbage text; now it's a clean I/O error (the config mismatch surfaces)
    (tmp_path / "B.DAT").write_bytes(encode_binary_file([[1, 2, 3]]))
    src = """      PROGRAM T
      DIMENSION M(3)
      OPEN(UNIT=1,FILE='B.DAT',ACCESS='SEQIN')
      READ(1) M
      END
"""
    with pytest.raises(OSError):
        forterp.run_source(src, dialect=forterp.FORTRAN10, target=forterp.PDP10, root=str(tmp_path))
