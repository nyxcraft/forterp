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

    def read(self, store, off: int, typ: str):
        w = store[off] & MASK36
        if typ == "REAL":
            return dec10_to_double(w)
        if typ == "DOUBLE PRECISION":
            return dec10_pair_to_double(w, store[off + 1] & MASK36)
        if typ == "COMPLEX":
            return complex(dec10_to_double(w), dec10_to_double(store[off + 1] & MASK36))
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
        else:  # INTEGER, LOGICAL, Hollerith: store the word bit-pattern
            store[off] = int(val) & MASK36
