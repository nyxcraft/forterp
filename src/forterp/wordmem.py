"""Word-addressable typed memory -- the substrate for faithful cross-type storage *punning* on the
value-model targets (PDP10 first; an LP64 byte-codec follows). A *store* is a flat list of machine
words; reads and writes go through the **accessing type's** codec, so EQUIVALENCE / COMMON aliasing
reinterprets the underlying bits exactly as the real machine does -- a REAL written and read back as
an INTEGER yields the genuine machine word, a DOUBLE's two words read as INTEGERs are the real
doubleword, and so on.

Today COMMON/EQUIVALENCE cells hold *typed Python values*, so cross-type aliasing is not
bit-faithful (a REAL cell holds a host float, not the DEC-10 word bits). This module is the
typed-view-over-raw-words that fixes that; the engine will route *punned* blocks through it
(monomorphic blocks keep the fast typed-cell path). See PUNNING-MEMORY-MODEL-DESIGN.md.

The PDP10 codec is the DEC FORTRAN-10 (KL10) representation, reusing `forbin`; its single/double
encodings are validated bit-for-bit against a real KL10 (SIMH KS10) -- see the test ground truth in
~/f66spec/notes/PDP10-PUNNING-PROBE*.OUT.
"""

from __future__ import annotations

from forterp.forbin import (
    MASK36,
    dec10_pair_to_double,
    dec10_to_double,
    double_to_dec10,
    double_to_dec10_pair,
)

# Storage units (machine words) a scalar of each type occupies (X3.9-1966 7.2.1.3.1.1): a double or
# complex datum is two words; integer, real, logical are one. Hollerith data lives in an integer.
STORAGE_UNITS = {
    "INTEGER": 1,
    "REAL": 1,
    "LOGICAL": 1,
    "DOUBLE PRECISION": 2,
    "COMPLEX": 2,
    "DOUBLE COMPLEX": 4,  # two doubles (re, im), two words each
}


def units(typ: str) -> int:
    """Words a scalar of this type occupies in word-addressable storage."""
    return STORAGE_UNITS.get(typ, 1)


class Pdp10WordMemory:
    """A typed accessor over a list of 36-bit machine words, in the DEC FORTRAN-10 representation.

    `store` is a plain list of ints (each a 36-bit word pattern, 0 .. 2**36-1). `read`/`write` take
    a word `off` and a FORTRAN type name and apply the KL10 codec for that type, so the same words
    read as different types reinterpret the bits faithfully."""

    def __init__(self, target):
        self.t = target  # for wrap() (signed 36-bit) and the logical convention

    @staticmethod
    def units(typ: str) -> int:
        return STORAGE_UNITS.get(typ, 1)

    @staticmethod
    def alloc(n: int) -> list:
        """A backing store of n addressable units (36-bit words), zero-filled."""
        return [0] * n

    def read(self, store, off: int, typ: str):
        w = store[off] & MASK36
        if typ == "REAL":
            return dec10_to_double(w)
        if typ == "DOUBLE PRECISION":
            return dec10_pair_to_double(w, store[off + 1] & MASK36)
        if typ == "COMPLEX":
            return complex(dec10_to_double(w), dec10_to_double(store[off + 1] & MASK36))
        if typ == "DOUBLE COMPLEX":  # two doubles (re, im), two words each
            return complex(
                dec10_pair_to_double(w, store[off + 1] & MASK36),
                dec10_pair_to_double(store[off + 2] & MASK36, store[off + 3] & MASK36),
            )
        # INTEGER, LOGICAL, Hollerith: the raw machine word as a signed integer
        return self.t.wrap(w)

    def write(self, store, off: int, typ: str, val) -> None:
        if typ == "REAL":
            store[off] = double_to_dec10(float(val))
        elif typ == "DOUBLE PRECISION":
            hi, lo = double_to_dec10_pair(float(val))
            store[off], store[off + 1] = hi, lo
        elif typ == "COMPLEX":
            v = val if isinstance(val, complex) else complex(float(val), 0.0)
            store[off] = double_to_dec10(v.real)
            store[off + 1] = double_to_dec10(v.imag)
        elif typ == "DOUBLE COMPLEX":  # two doubles (re, im), two words each
            v = val if isinstance(val, complex) else complex(float(val), 0.0)
            store[off], store[off + 1] = double_to_dec10_pair(v.real)
            store[off + 2], store[off + 3] = double_to_dec10_pair(v.imag)
        else:  # INTEGER, LOGICAL, Hollerith: store the word bit-pattern
            store[off] = int(val) & MASK36


# ---- LP64 / IEEE codec: the byte-addressable backend (P2) ---------------------------------------
import struct as _struct  # noqa: E402  (kept module-local to the LP64 backend)

# Cached Struct objects (little-endian, the x86_64 / LP64 layout gfortran emits). DOUBLE COMPLEX is
# not modeled here yet. Hollerith / unknown types read as the 4-byte integer word.
_LP64 = {
    "INTEGER": _struct.Struct("<i"),
    "REAL": _struct.Struct("<f"),
    "DOUBLE PRECISION": _struct.Struct("<d"),
    "LOGICAL": _struct.Struct("<i"),
}
_LP64_SINGLE = _struct.Struct("<f")  # the two halves of a COMPLEX
_LP64_DOUBLE = _struct.Struct("<d")  # the two halves of a DOUBLE COMPLEX
_LP64_SIZE = {
    "INTEGER": 4,
    "REAL": 4,
    "DOUBLE PRECISION": 8,
    "COMPLEX": 8,
    "DOUBLE COMPLEX": 16,
    "LOGICAL": 4,
}


def _to_i32(v: int) -> int:
    """Wrap an integer into signed 32-bit two's complement (so struct '<i' never overflows)."""
    v = int(v) & 0xFFFFFFFF
    return v - (1 << 32) if v & (1 << 31) else v


class Lp64LeByteMemory:
    """A typed accessor over a `bytearray`, in the **little-endian** LP64 / IEEE representation
    (REAL=4 bytes, DOUBLE=8, INTEGER=4) -- exactly what gfortran emits on x86_64 / ARM64. `off` is a
    BYTE offset; reads/writes go through Python `struct` (the `<` formats), so cross-type aliasing
    reinterprets the bytes the way the real machine does. This is the byte-addressable sibling of
    `Pdp10WordMemory`; the bit patterns are validated against gfortran (see the PoC + test ground
    truth).

    "Le" is in the name on purpose: LP64 fixes the integer/pointer widths but NOT byte order, and
    a big-endian 64-bit machine (s390x, SPARC64) lays the same values out mirror-reversed -- that
    would be a separate codec (the `>` formats), not this one."""

    def __init__(self, target=None):
        self.t = target  # unused for the IEEE codec; kept for interface symmetry

    @staticmethod
    def units(typ: str) -> int:
        """Bytes a scalar of this type occupies."""
        return _LP64_SIZE.get(typ, 4)

    @staticmethod
    def alloc(n: int) -> bytearray:
        """A backing store of n addressable units (bytes), zero-filled."""
        return bytearray(n)

    def read(self, store, off: int, typ: str):
        if typ == "COMPLEX":
            re = _LP64_SINGLE.unpack_from(store, off)[0]
            im = _LP64_SINGLE.unpack_from(store, off + 4)[0]
            return complex(re, im)
        if typ == "DOUBLE COMPLEX":
            re = _LP64_DOUBLE.unpack_from(store, off)[0]
            im = _LP64_DOUBLE.unpack_from(store, off + 8)[0]
            return complex(re, im)
        return _LP64.get(typ, _LP64["INTEGER"]).unpack_from(store, off)[0]

    def write(self, store, off: int, typ: str, val) -> None:
        if typ == "COMPLEX":
            v = val if isinstance(val, complex) else complex(float(val), 0.0)
            _LP64_SINGLE.pack_into(store, off, v.real)
            _LP64_SINGLE.pack_into(store, off + 4, v.imag)
        elif typ == "DOUBLE COMPLEX":
            v = val if isinstance(val, complex) else complex(float(val), 0.0)
            _LP64_DOUBLE.pack_into(store, off, v.real)
            _LP64_DOUBLE.pack_into(store, off + 8, v.imag)
        elif typ in ("REAL", "DOUBLE PRECISION"):
            _LP64[typ].pack_into(store, off, float(val))
        else:  # INTEGER, LOGICAL, Hollerith: the 4-byte two's-complement word
            _LP64["INTEGER"].pack_into(store, off, _to_i32(val))


# ---- VAX codec: little-endian integers, MIDDLE-endian (word-swapped) floats (best effort) -------
# UNVALIDATED: no VAX hardware or simulator oracle has been checked against this yet (the VAX target
# is itself provisional). The format is from the published VAX architecture: INTEGER is plain
# little-endian; F_floating (REAL, 4 bytes) and D_floating (DOUBLE, 8 bytes) store their 16-bit
# words in PDP-11 "middle-endian" order -- the sign/exponent word is at the LOW address, and the
# 32-/64-bit value is the words swapped relative to a straight little-endian read. Both use an 8-bit
# excess-128 exponent and a hidden-bit mantissa normalized to [0.5, 1.0) -- the same value formula
# as the PDP-10 float, only narrower and word-swapped. Anchored by the canonical F_float 1.0 =
# 0x00004080 (bytes 80 40 00 00). DOUBLE is D_floating (the VAX FORTRAN default; /G_FLOATING is not
# modeled). When a VAX oracle exists, validate as the PDP-10 probe did and correct as needed.

_VAX_SIZE = {
    "INTEGER": 4,
    "REAL": 4,
    "DOUBLE PRECISION": 8,
    "COMPLEX": 8,
    "DOUBLE COMPLEX": 16,
    "LOGICAL": 4,
}


def _vax_f_decode(store, off: int) -> float:
    lo = store[off] | (store[off + 1] << 8)  # sign/exp/high-fraction word (low address)
    hi = store[off + 2] | (store[off + 3] << 8)  # low-fraction word
    fp = (lo << 16) | hi  # the conventional 32-bit value, sign at bit 31
    e = (fp >> 23) & 0xFF
    if e == 0:  # true zero (s=0); s=1,e=0 is a reserved operand -- treat as 0 (best effort)
        return 0.0
    m = (0x800000 | (fp & 0x7FFFFF)) / 16777216.0  # (2^23 + f) / 2^24, in [0.5, 1)
    v = m * (2.0 ** (e - 128))
    return -v if (fp >> 31) else v


def _vax_f_encode(store, off: int, x: float) -> None:
    x = float(x)
    if x == 0.0:
        store[off : off + 4] = b"\x00\x00\x00\x00"
        return
    import math

    s = 1 if x < 0 else 0
    m, e = math.frexp(abs(x))  # m in [0.5, 1)
    full = round(m * 16777216.0)
    if full >= (1 << 24):  # rounding carried into 1.0
        full >>= 1
        e += 1
    big_e = e + 128
    if not (1 <= big_e <= 255):
        raise OverflowError(f"{x!r} is out of VAX F_floating range")
    fp = (s << 31) | ((big_e & 0xFF) << 23) | (full & 0x7FFFFF)
    lo, hi = (fp >> 16) & 0xFFFF, fp & 0xFFFF
    store[off], store[off + 1] = lo & 0xFF, lo >> 8
    store[off + 2], store[off + 3] = hi & 0xFF, hi >> 8


def _vax_d_decode(store, off: int) -> float:
    w = [store[off + 2 * k] | (store[off + 2 * k + 1] << 8) for k in range(4)]
    fp = (w[0] << 48) | (w[1] << 32) | (w[2] << 16) | w[3]  # word 0 (sign/exp) at low address
    e = (fp >> 55) & 0xFF
    if e == 0:
        return 0.0
    m = ((1 << 55) | (fp & ((1 << 55) - 1))) / float(1 << 56)  # (2^55 + f)/2^56, in [0.5, 1)
    v = m * (2.0 ** (e - 128))
    return -v if (fp >> 63) else v


def _vax_d_encode(store, off: int, x: float) -> None:
    x = float(x)
    if x == 0.0:
        store[off : off + 8] = b"\x00" * 8
        return
    import math

    s = 1 if x < 0 else 0
    m, e = math.frexp(abs(x))
    full = round(m * float(1 << 56))
    if full >= (1 << 56):
        full >>= 1
        e += 1
    big_e = e + 128
    if not (1 <= big_e <= 255):  # D_floating shares F's 8-bit exponent range (~1e38)
        raise OverflowError(f"{x!r} is out of VAX D_floating range")
    fp = (s << 63) | ((big_e & 0xFF) << 55) | (full & ((1 << 55) - 1))
    for k in range(4):
        w = (fp >> (48 - 16 * k)) & 0xFFFF
        store[off + 2 * k], store[off + 2 * k + 1] = w & 0xFF, w >> 8


class VaxByteMemory:
    """A typed accessor over a `bytearray` in the VAX representation: little-endian INTEGER, and
    MIDDLE-endian (word-swapped) F_floating / D_floating for REAL / DOUBLE PRECISION. The byte-
    addressable sibling of `Pdp10WordMemory` for the VAX value model.

    BEST EFFORT / UNVALIDATED: no VAX oracle has been checked yet (the VAX target is provisional).
    Anchored by the canonical F_float 1.0 = 0x00004080; correct against a real VAX/simulator when
    one is available."""

    def __init__(self, target=None):
        self.t = target

    @staticmethod
    def units(typ: str) -> int:
        return _VAX_SIZE.get(typ, 4)

    @staticmethod
    def alloc(n: int) -> bytearray:
        return bytearray(n)

    def read(self, store, off: int, typ: str):
        if typ == "REAL":
            return _vax_f_decode(store, off)
        if typ == "DOUBLE PRECISION":
            return _vax_d_decode(store, off)
        if typ == "COMPLEX":
            return complex(_vax_f_decode(store, off), _vax_f_decode(store, off + 4))
        if typ == "DOUBLE COMPLEX":  # two D_floating doubles (re, im)
            return complex(_vax_d_decode(store, off), _vax_d_decode(store, off + 8))
        return _LP64["INTEGER"].unpack_from(store, off)[0]  # INTEGER/LOGICAL: plain LE int32

    def write(self, store, off: int, typ: str, val) -> None:
        if typ == "REAL":
            _vax_f_encode(store, off, float(val))
        elif typ == "DOUBLE PRECISION":
            _vax_d_encode(store, off, float(val))
        elif typ == "COMPLEX":
            v = val if isinstance(val, complex) else complex(float(val), 0.0)
            _vax_f_encode(store, off, v.real)
            _vax_f_encode(store, off + 4, v.imag)
        elif typ == "DOUBLE COMPLEX":  # two D_floating doubles (re, im)
            v = val if isinstance(val, complex) else complex(float(val), 0.0)
            _vax_d_encode(store, off, v.real)
            _vax_d_encode(store, off + 8, v.imag)
        else:  # INTEGER / LOGICAL / Hollerith: little-endian two's-complement 32-bit
            _LP64["INTEGER"].pack_into(store, off, _to_i32(val))
