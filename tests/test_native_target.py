"""The portable NATIVE target -- the library default. Standard FORTRAN-66 on a clean
64-bit host machine: 64-bit two's-complement integers, .TRUE.=1 with BOOLEAN logical
operators, and 8-bit ASCII packed into integers. These check the three value-model axes
where NATIVE deliberately differs from the faithful PDP-10 target (which the rest of the
suite validates). Broad conformance under NATIVE is covered by the FCVS corpus run
(test_fcvs_conformance.test_native_target_runs_the_corpus_identically)."""

import f66
from f66 import fmt
from f66.target import PDP10, NATIVE
from conftest import run, run_int, out


# ---- the library default IS NATIVE (the headline of the value-model work) --------
def test_library_default_target_is_native():
    # `import f66; run_source(...)` must use NATIVE, not the PDP-10 quirk model. Checked
    # via the public API (conftest pins PDP10 for the unit suite, so it can't see this).
    assert f66.Engine({}).tgt is f66.NATIVE
    assert f66.run_source("      PROGRAM T\n      END\n").tgt is f66.NATIVE


# ---- axis 1: integers are 64-bit, not 36-bit -------------------------------------
def test_native_wrap_is_64bit():
    assert NATIVE.wrap(2**63 - 1) == 2**63 - 1
    assert NATIVE.wrap(2**63) == -(2**63)            # two's-complement wrap at 64 bits
    assert NATIVE.wrap(2**40) == 2**40               # no 36-bit wrap ...
    assert PDP10.wrap(2**40) != 2**40                # ... which PDP-10 does


def test_native_program_no_36bit_overflow():
    # 1_000_000 * 1_000_000 = 1e12 overflows 36 bits (PDP-10 wraps negative) but fits 64.
    body = "        V(1) = 1000000 * 1000000\n"
    assert out(run_int(body, target=NATIVE), 1) == 1_000_000_000_000
    assert out(run_int(body, target=PDP10), 1) != 1_000_000_000_000   # PDP-10 wraps


# ---- axis 2: logicals are 1/0 with boolean (not bitwise) operators ---------------
def test_native_logical_values_and_ops():
    assert NATIVE.from_bool(True) == 1 and NATIVE.from_bool(False) == 0
    assert NATIVE.truthy(1) and NATIVE.truthy(5) and not NATIVE.truthy(0)
    assert NATIVE.lnot(1) == 0 and NATIVE.lnot(0) == 1
    assert NATIVE.land(1, 0) == 0 and NATIVE.lor(0, 1) == 1


def test_native_program_true_is_one():
    # a relational result stored into an integer slot: NATIVE 1, PDP-10 -1.
    body = "        V(1) = (3 .GT. 2)\n"
    assert out(run_int(body, target=NATIVE), 1) == 1
    assert out(run_int(body, target=PDP10), 1) == -1


# ---- axis 3: 8-bit ASCII packed into integers ------------------------------------
def test_native_char_8bit_roundtrip():
    assert NATIVE.unpack(NATIVE.pack("Hi!"), 3) == "Hi!"
    # an 8th-bit (high) byte survives under NATIVE; PDP-10's 7 bits mask it away.
    assert NATIVE.unpack(NATIVE.pack(chr(0xC9)), 1) == chr(0xC9)
    assert PDP10.unpack(PDP10.pack(chr(0xC9)), 1) == chr(0xC9 & 0x7F)


def test_native_char_comparison_is_ascii_monotonic():
    # packed chars compare in ASCII order (left-justified big-endian), like PDP-10.
    assert NATIVE.pack("A") < NATIVE.pack("B")
    assert NATIVE.pack("AA") < NATIVE.pack("AB")


def test_native_hollerith_parameter_matches_literal():
    # A Hollerith PARAMETER must compare equal to a literal of the same text: the
    # constant is packed by the engine's target, not hard-coded PDP-10 at parse time.
    src = ("        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n"
           "        COMMON /OUT/ V(40)\n        PARAMETER (C = 'X')\n"
           "        V(1) = 0\n        IF (C .EQ. 'X') V(1) = 1\n        END\n")
    assert out(run(src, target=NATIVE), 1) == 1
    assert out(run(src, target=PDP10), 1) == 1


# ---- step 1: INT-family + LSH intrinsics follow the engine's target --------------
def test_native_int_and_lsh_intrinsics_follow_target():
    # INT() and LSH() wrap in the target's word: INT(2.0**40) and LSH(1,40) keep full
    # width on NATIVE (64-bit) but vanish to 0 on PDP-10 (2**40 is a multiple of 2**36).
    for body in ("        V(1) = INT(2.0E0 ** 40)\n", "        V(1) = LSH(1, 40)\n"):
        assert out(run_int(body, target=NATIVE), 1) == 2**40
        assert out(run_int(body, target=PDP10), 1) == 0


# ---- step 2: .EQV./.XOR. are boolean (not bitwise) under NATIVE ------------------
def test_native_eqv_xor_are_boolean():
    assert NATIVE.lxor(1, 0) == 1 and NATIVE.lxor(1, 1) == 0
    assert NATIVE.leqv(1, 1) == 1 and NATIVE.leqv(1, 0) == 0


# ---- pin fix: the O (octal) descriptor width follows the target word -------------
def test_native_o_format_width_follows_target():
    items = fmt.parse_format("(O24)")
    assert fmt.render(items, [-1], PDP10)[0] == "000000000000777777777777"    # 36-bit word
    assert fmt.render(items, [-1], NATIVE)[0] == "001777777777777777777777"   # 64-bit word
