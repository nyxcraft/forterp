"""Direct unit tests of the interpreter's core numeric/word primitives."""

from f66.engine import wrap36, trunc_div, fort_mod, packword, linidx, _lsh
from f66.parser import pack5
from f66.fmt import unpack_chars
from f66.target import PDP10

WORD = 1 << 36
P35 = 1 << 35


# ---- wrap36: signed two's-complement 36-bit ----
def test_wrap36_identity_small():
    assert wrap36(0) == 0
    assert wrap36(1) == 1
    assert wrap36(P35 - 1) == P35 - 1            # largest positive

def test_wrap36_sign_bit():
    assert wrap36(P35) == -P35                   # sign bit set -> negative
    assert wrap36(WORD - 1) == -1                # all ones -> -1
    assert wrap36(-P35) == -P35

def test_wrap36_wraps_modulo_word():
    assert wrap36(WORD) == 0
    assert wrap36(WORD + 5) == 5
    assert wrap36(-1) == -1
    assert wrap36(-WORD - 1) == -1


# ---- integer division: truncate toward zero (NOT floor) ----
def test_trunc_div_signs():
    assert trunc_div(7, 2) == 3
    assert trunc_div(-7, 2) == -3                # toward zero, not -4
    assert trunc_div(7, -2) == -3
    assert trunc_div(-7, -2) == 3
    assert trunc_div(1, 2) == 0
    assert trunc_div(-1, 2) == 0
    assert trunc_div(6, 3) == 2


# ---- MOD: result takes the sign of the dividend ----
def test_fort_mod_int_signs():
    assert fort_mod(17, 5) == 2
    assert fort_mod(-17, 5) == -2
    assert fort_mod(17, -5) == 2
    assert fort_mod(-17, -5) == -2
    assert fort_mod(15, 5) == 0

def test_fort_mod_real():
    assert fort_mod(5.5, 2.0) == 1.5
    assert fort_mod(-5.5, 2.0) == -1.5


# ---- LSH: logical (unsigned) shift of a 36-bit word ----
def test_lsh_left_right():
    assert _lsh(PDP10, 1, 4) == 16
    assert _lsh(PDP10, 16, -4) == 1
    assert _lsh(PDP10, 0o777, 0) == 0o777

def test_lsh_into_sign_bit():
    assert _lsh(PDP10, 1, 35) == -P35            # shifted into the sign bit

def test_lsh_right_is_logical_not_arithmetic():
    # -1 is all 36 ones; a logical >>1 fills with 0 -> 2^35-1, not -1
    assert _lsh(PDP10, -1, -1) == P35 - 1
    assert _lsh(PDP10, -P35, -35) == 1


# ---- packed ASCII (7-bit, left-justified, blank-padded, signed) ----
def test_pack5_known_filename():
    # GAM:X.A filename word, from the missing-maps analysis (signed 36-bit)
    assert pack5("X.A  ") == -21279760320

def test_pack5_blank_pads():
    assert pack5("X.A") == pack5("X.A  ")
    assert packword("HI") == pack5("HI")

def test_pack5_roundtrip():
    assert unpack_chars(packword("HELLO"), 5) == "HELLO"
    assert unpack_chars(packword("X.A  "), 5) == "X.A  "
    assert unpack_chars(packword("AB"), 5) == "AB   "


# ---- linidx: column-major, honoring (lo,hi) bounds ----
def test_linidx_1d():
    assert linidx([1], [(1, 10)]) == 0
    assert linidx([10], [(1, 10)]) == 9

def test_linidx_lower_bounds():
    assert linidx([0], [(0, 3)]) == 0
    assert linidx([3], [(0, 3)]) == 3
    assert linidx([1501], [(1501, 3000)]) == 0   # COMMON /CODE/ lower bound

def test_linidx_2d_column_major():
    dims = [(1, 3), (1, 4)]
    assert linidx([1, 1], dims) == 0
    assert linidx([2, 1], dims) == 1             # first subscript varies fastest
    assert linidx([1, 2], dims) == 3             # second subscript strides by 3
    assert linidx([3, 4], dims) == 11


# ---- OPEN device-handler registry (game-agnostic interpreter core) ----
def test_open_device_registry_dispatches():
    # OPEN ... DEVICE='X' dispatches to a handler registered via register_device, so the
    # core knows only TTY + files; Empire's GAM: terrain device plugs in exactly this way.
    from conftest import run, out

    def setup(eng):
        def zap(e, unit, specs, frame):
            e.io[unit] = {"recs": [[11, 22, 33]], "pos": 0, "mode": "r"}
        eng.register_device("ZAP", zap)

    src = ("        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n"
           "        COMMON /OUT/ V(40)\n        DIMENSION REC(3)\n"
           "        OPEN(UNIT=1,DEVICE='ZAP',FILE='X',ACCESS='SEQIN')\n"
           "        READ(1) REC\n"
           "        V(1)=REC(1)\n        V(2)=REC(2)\n        V(3)=REC(3)\n"
           "        END\n")
    eng = run(src, setup=setup)
    assert [out(eng, i) for i in (1, 2, 3)] == [11, 22, 33]


def test_engine_value_model_is_target_pluggable():
    # The engine routes its value model through an injected Target (target.py), so the
    # core is representation-agnostic: a 16-bit target wraps arithmetic differently than
    # the PDP-10's 36 -- proof the seam is real, not cosmetic.
    from conftest import run, out, HEAD, TAIL
    from f66.target import Target
    src = HEAD + "        V(1) = 50000 + 50000\n" + TAIL
    assert out(run(src), 1) == 100000                       # default PDP-10 (36-bit)
    eng16 = run(src, setup=lambda e: setattr(e, "tgt", Target(word_bits=16)))
    assert out(eng16, 1) == -31072                          # 100000 wrapped signed-16
