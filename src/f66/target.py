"""The machine value model an f66 program runs against -- the seam between the generic
FORTRAN-66 core and a specific target environment.

A Target fixes the three things that make values machine-dependent: the word width +
signed-integer wrap, how characters pack into a word, and the logical-truth convention.
PDP-10/SIXBIT (36-bit words, 5 seven-bit chars/word, .TRUE.=-1) is the default and the
only target we ship; a portable target would differ.  The Engine holds one
(`Engine(..., target=...)`) and routes its value model through it, so the core itself
is representation-agnostic.  See [[package-breakup-plan]] / [[value-model-packed-ascii]].
"""
from __future__ import annotations


class Target:
    def __init__(self, word_bits=36, chars_per_word=5, logical_true=-1,
                 bitwise_logic=True, bits_per_char=7):
        self.word_bits = word_bits
        self.chars_per_word = chars_per_word
        self.bits_per_char = bits_per_char    # PDP-10: 7-bit ASCII, 5 to a 36-bit word
        self.logical_true = logical_true
        self.bitwise_logic = bitwise_logic    # PDP-10 .AND./.OR. act on the word's bits
        self.mask = (1 << word_bits) - 1
        self.sign = 1 << (word_bits - 1)

    def wrap(self, v: int) -> int:
        """Reduce an integer to a signed word value (PDP-10: 2's-complement, 36 bits)."""
        v &= self.mask
        return v - (1 << self.word_bits) if v & self.sign else v

    def truthy(self, v) -> bool:
        """Is this value .TRUE.? PDP-10 (logical_true=-1, all bits set): the sign is
        negative. A target with a positive logical_true: any nonzero value."""
        if isinstance(v, bool):
            return v
        return v < 0 if self.logical_true < 0 else v != 0

    def from_bool(self, b) -> int:
        """A relational/logical result as this target's logical value (PDP-10: -1/0)."""
        return self.logical_true if b else 0

    # ---- logical connectives: bitwise on the word (PDP-10) or boolean (portable) ----
    def lnot(self, v):
        return self.wrap(~int(v)) if self.bitwise_logic else self.from_bool(not self.truthy(v))

    def land(self, l, r):
        return (self.wrap(int(l) & int(r)) if self.bitwise_logic
                else self.from_bool(self.truthy(l) and self.truthy(r)))

    def lor(self, l, r):
        return (self.wrap(int(l) | int(r)) if self.bitwise_logic
                else self.from_bool(self.truthy(l) or self.truthy(r)))

    def lxor(self, l, r):
        return (self.wrap(int(l) ^ int(r)) if self.bitwise_logic
                else self.from_bool(self.truthy(l) != self.truthy(r)))

    def leqv(self, l, r):
        return (self.wrap(~(int(l) ^ int(r))) if self.bitwise_logic
                else self.from_bool(self.truthy(l) == self.truthy(r)))

    def pack(self, s: str) -> int:
        """Pack up to chars_per_word characters left-justified, blank-padded, into one
        signed word (bits_per_char bits each; PDP-10: 5 chars x 7 bits in 36 bits)."""
        cw, bpc = self.chars_per_word, self.bits_per_char
        s = (s + " " * cw)[:cw]
        cmask = (1 << bpc) - 1
        top = self.word_bits - bpc
        v = 0
        for i, c in enumerate(s):
            v |= (ord(c) & cmask) << (top - bpc * i)
        return self.wrap(v)

    def unpack(self, w, n=None) -> str:
        """Unpack up to n leading characters from a packed word (default chars_per_word).
        A value that is already a Python str is returned as-is (sliced to n)."""
        if isinstance(w, str):
            return w[:n] if n else w
        cw, bpc = self.chars_per_word, self.bits_per_char
        cmask = (1 << bpc) - 1
        top = self.word_bits - bpc
        u = int(w) & self.mask
        out = []
        for k in range(min(n, cw) if n else cw):
            c = (u >> (top - bpc * k)) & cmask
            out.append(chr(c) if c else " ")
        return "".join(out)


PDP10 = Target()          # faithful DEC PDP-10: 36-bit, 5x7-bit packed ASCII, .TRUE.=-1

# The portable host-native target and the default: a clean 64-bit machine for running
# standard FORTRAN-66 without PDP-10 quirks -- 64-bit two's-complement integers, 8-bit
# ASCII (8 chars/word), .TRUE.=1 with boolean (not bitwise) logical operators.
NATIVE = Target(word_bits=64, chars_per_word=8, bits_per_char=8,
                logical_true=1, bitwise_logic=False)
