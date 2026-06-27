"""The machine value model an forterp program runs against -- the seam between the generic
FORTRAN-66 core and a specific machine.

A Target fixes what makes values machine-dependent: the word width + signed-integer
wrap, how characters pack into a word (width, bits-per-char, byte order), the
logical-truth convention, and whether the logical connectives are bit-wise. The Engine
holds one (`Engine(..., target=...)`) and routes its whole value model through it, so the
core itself is representation-agnostic. Shipped targets: NATIVE (the default -- a portable
64-bit host), PDP10 (faithful DEC FORTRAN-10: 36-bit words, 5x7-bit packing, .TRUE.=-1),
LP64LE (a 64-bit little-endian IEEE machine -- matches gfortran on x86_64), and VAX
(provisional, unvalidated).

A target may also name a `mem_model` -- the word-addressable codec used for faithful cross-type
storage punning under the engine's `word_memory` flag (PDP10 = 36-bit KL10 words; LP64LE = LE IEEE
bytes; VAX = middle-endian F/D floats). See forterp.wordmem.
"""

from __future__ import annotations


class Target:
    def __init__(
        self,
        word_bits=36,
        chars_per_word=5,
        logical_true=-1,
        bitwise_logic=True,
        bits_per_char=7,
        little_endian=False,
        truth=None,
        ieee_math=False,
        packed_double=False,
        mem_model=None,
    ):
        self.word_bits = word_bits
        self.chars_per_word = chars_per_word
        self.bits_per_char = bits_per_char  # PDP-10: 7-bit ASCII, 5 to a 36-bit word
        self.little_endian = little_endian  # char 0 in the LOW byte (VAX) vs high (PDP-10)
        self.logical_true = logical_true
        self.bitwise_logic = bitwise_logic  # PDP-10 .AND./.OR. act on the word's bits
        # truth test: "sign" (v<0), "nonzero" (v!=0), "low_bit" (v&1); None = derive from
        # logical_true's sign (PDP-10 -> sign, a positive logical_true -> nonzero).
        self.truth = truth
        # ieee_math: how an undefined arithmetic result is delivered (§6 prohibits these ops, so
        # any value conforms). True (NATIVE) -> IEEE Inf/NaN, matching gfortran; False (PDP-10/VAX)
        # -> FOROTS's non-fatal recovery (0.0 on divide, |x| stand-ins, with a LIB warning).
        self.ieee_math = ieee_math
        # packed_double: a storage-associated DOUBLE PRECISION scalar is stored as its two genuine
        # machine words (the KL10 high/low doubleword, via forbin), so an INTEGER EQUIVALENCEd onto
        # those words reads the real machine words -- faithful to FORTRAN-10. False (NATIVE/VAX):
        # the value lives in the first cell with a zero shadow in the second (count-accurate only).
        self.packed_double = packed_double
        # mem_model: which word-addressable codec `word_memory` uses for faithful storage punning
        # (None = no faithful codec; the engine falls back to typed cells). "pdp10" = 36-bit KL10
        # words (forbin); "lp64le" = little-endian LP64/IEEE bytes (struct). See forterp.wordmem.
        self.mem_model = mem_model
        self.mask = (1 << word_bits) - 1
        self.sign = 1 << (word_bits - 1)
        self.modulus = 1 << word_bits  # 2^word_bits: the two's-complement wrap modulus
        self.char_mask = (1 << bits_per_char) - 1  # low-bits mask for one packed character

    def _charshift(self, i):
        """Bit offset of the i-th packed character. Big-endian (PDP-10/NATIVE): char 0 in
        the high bits. Little-endian (VAX): char 0 in the low bits."""
        bpc = self.bits_per_char
        return bpc * i if self.little_endian else self.word_bits - bpc - bpc * i

    def wrap(self, v: int) -> int:
        """Reduce an integer to a signed word value (PDP-10: 2's-complement, 36 bits)."""
        v &= self.mask
        return v - self.modulus if v & self.sign else v

    def truthy(self, v) -> bool:
        """Is this value .TRUE.?  PDP-10: sign-negative; NATIVE: nonzero; VAX: low-order
        bit set. With truth=None, derive from logical_true's sign (back-compat)."""
        if isinstance(v, bool):
            return v
        m = self.truth
        if m == "low_bit":
            return (int(v) & 1) == 1
        if m == "nonzero":
            return v != 0
        if m == "sign":
            return v < 0
        return v < 0 if self.logical_true < 0 else v != 0

    def from_bool(self, b) -> int:
        """A relational/logical result as this target's logical value (PDP-10: -1/0)."""
        return self.logical_true if b else 0

    # ---- logical connectives ----
    def _connective(self, bitwise, boolean):
        """Apply one logical connective under this target's convention: `bitwise()` on the
        raw words (PDP-10 -- .TRUE. is all-bits-set, so the bit ops carry the truth), or
        `boolean()` on the truth values (portable). Only the chosen branch is evaluated."""
        return self.wrap(bitwise()) if self.bitwise_logic else self.from_bool(boolean())

    def lnot(self, v):
        return self._connective(lambda: ~int(v), lambda: not self.truthy(v))

    def land(self, lhs, rhs):
        return self._connective(
            lambda: int(lhs) & int(rhs), lambda: self.truthy(lhs) and self.truthy(rhs)
        )

    def lor(self, lhs, rhs):
        return self._connective(
            lambda: int(lhs) | int(rhs), lambda: self.truthy(lhs) or self.truthy(rhs)
        )

    def lxor(self, lhs, rhs):
        return self._connective(
            lambda: int(lhs) ^ int(rhs), lambda: self.truthy(lhs) != self.truthy(rhs)
        )

    def leqv(self, lhs, rhs):
        return self._connective(
            lambda: ~(int(lhs) ^ int(rhs)), lambda: self.truthy(lhs) == self.truthy(rhs)
        )

    def pack(self, s: str) -> int:
        """Pack up to chars_per_word characters left-justified, blank-padded, into one
        signed word (bits_per_char bits each; PDP-10: 5 chars x 7 bits in 36 bits)."""
        cw = self.chars_per_word
        s = (s + " " * cw)[:cw]
        v = 0
        for i, c in enumerate(s):
            v |= (ord(c) & self.char_mask) << self._charshift(i)
        return self.wrap(v)

    def unpack(self, w, n=None) -> str:
        """Unpack up to n leading characters from a packed word (default chars_per_word).
        A value that is already a Python str is returned as-is (sliced to n)."""
        if isinstance(w, str):
            return w[:n] if n else w
        cw = self.chars_per_word
        u = int(w) & self.mask
        out = []
        for k in range(min(n, cw) if n else cw):
            c = (u >> self._charshift(k)) & self.char_mask
            out.append(chr(c) if c else " ")
        return "".join(out)


PDP10 = Target(packed_double=True, mem_model="pdp10")  # faithful DEC PDP-10: 36-bit, packed ASCII

# The portable host-native target and the default: a clean 64-bit machine for running
# standard FORTRAN-66 without PDP-10 quirks -- 64-bit two's-complement integers, 8-bit
# ASCII (8 chars/word), .TRUE.=1 with boolean (not bitwise) logical operators.
NATIVE = Target(
    word_bits=64,
    chars_per_word=8,
    bits_per_char=8,
    logical_true=1,
    bitwise_logic=False,
    ieee_math=True,  # undefined math -> IEEE Inf/NaN (matches gfortran), not FOROTS recovery
)

# PROVISIONAL, UNVALIDATED guess at the VAX-11 / VAX FORTRAN value model -- no driver or
# real compiler/manual has been checked against this yet. Best current understanding:
# 32-bit two's-complement integers; 8-bit ASCII packed 4-per-longword LITTLE-ENDIAN (char
# 0 in the low byte), so Hollerith-in-INTEGER does NOT compare in string order; LOGICAL
# .TRUE.=-1 / .FALSE.=0 with a LOW-ORDER-BIT truth test; .AND./.OR. bit-wise on the word.
# REAL is modeled as a Python float (we do NOT reproduce VAX F_floating bit-for-bit -- the
# same approximation as PDP10/NATIVE). Things to verify against a VAX FORTRAN reference:
# the .TRUE. constant value, the exact truth test, byte order for A-format, and whether
# logical ops are bit-wise.
VAX = Target(
    word_bits=32,
    chars_per_word=4,
    bits_per_char=8,
    logical_true=-1,
    bitwise_logic=True,
    little_endian=True,
    truth="low_bit",
    mem_model="vax",  # word_memory: LE ints, middle-endian F/D floats (best-effort, unvalidated)
)

# The modern 64-bit IEEE machine -- the little-endian LP64 data model gfortran targets on
# x86_64/ARM64: default
# INTEGER and REAL are 32-bit, DOUBLE PRECISION 64-bit, 8-bit ASCII packed 4-per-word little-endian,
# .TRUE.=1 with boolean logical operators. Its reason to exist is the `lp64le` memory codec: with
# word_memory on, COMMON/EQUIVALENCE punning is byte-faithful and matches gfortran bit-for-bit
# (see forterp.wordmem.Lp64LeByteMemory). "le" = little-endian; a big-endian 64-bit target is TBD.
LP64LE = Target(
    word_bits=32,
    chars_per_word=4,
    bits_per_char=8,
    logical_true=1,
    bitwise_logic=False,
    little_endian=True,
    ieee_math=True,
    mem_model="lp64le",
)

# CLI / front-end name -> value model, so every caller resolves the same names in one place.
TARGETS = {"native": NATIVE, "pdp10": PDP10, "vax": VAX, "lp64le": LP64LE}
