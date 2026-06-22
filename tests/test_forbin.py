"""FOROTS binary record codec (forbin.py) -- validated against the FORTRAN-10
V5 manual, Appendix D.5.2 (the LSCW format and its D-6 worked example).
"""

import math

import pytest

from forterp.forbin import (
    Dec10FloatError,
    dec10_to_double,
    decode_record,
    double_to_dec10,
    encode_record,
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
