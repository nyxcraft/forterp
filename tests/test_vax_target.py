"""PROVISIONAL VAX-11 target -- a best-effort GUESS, not yet validated against a real VAX
FORTRAN compiler/manual or a driver. These tests pin the value model *as currently
implemented* so it doesn't drift silently; they are NOT evidence the model is correct.
What needs checking against a VAX FORTRAN reference is listed in the VAX comment in
target.py.

Encoded model: 32-bit two's-complement integers; 8-bit ASCII packed 4-per-longword
LITTLE-ENDIAN (char 0 in the low byte -> Hollerith-in-INTEGER is NOT string-monotonic);
.TRUE.=-1/.FALSE.=0 with a LOW-ORDER-BIT truth test; bit-wise .AND./.OR.. REAL is a Python
float (VAX F_floating is not modeled bit-for-bit -- same approximation as PDP10/NATIVE)."""

from forterp.target import VAX, PDP10
from conftest import run_int, out


def test_vax_integer_is_32bit():
    assert VAX.wrap(2**31 - 1) == 2**31 - 1
    assert VAX.wrap(2**31) == -(2**31)  # two's-complement wrap at 32 bits


def test_vax_char_packing_is_little_endian():
    # round-trips, but the first char in the low byte breaks ASCII ordering under
    # arithmetic comparison -- the documented VAX quirk vs PDP-10's big-endian packing.
    assert VAX.unpack(VAX.pack("ABCD"), 4) == "ABCD"
    assert VAX.pack("AZ") > VAX.pack("BA")  # little-endian: NOT string order
    assert PDP10.pack("AZ") < PDP10.pack("BA")  # big-endian PDP-10 IS string order


def test_vax_truth_is_low_order_bit():
    assert VAX.from_bool(True) == -1 and VAX.from_bool(False) == 0
    assert VAX.truthy(-1) and not VAX.truthy(0)
    assert VAX.truthy(1) and not VAX.truthy(2)  # odd = true, even = false (bit 0)
    assert not VAX.truthy(-2)  # even -> false; PDP-10's sign test says true
    assert PDP10.truthy(-2)  # ... the distinguishing case


def test_vax_program_runs_end_to_end():
    # smoke: a small program executes under VAX with 32-bit arithmetic and low-bit logic.
    eng = run_int(
        "        V(1) = 50000 + 50000\n        V(2) = 0\n        IF (7 .GT. 3) V(2) = 1\n",
        target=VAX,
    )
    assert out(eng, 1) == 100000  # fits 32 bits, no wrap
    assert out(eng, 2) == 1  # relational true -> stored, low-bit true
