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

from f66.parser import pack5
from f66.fmt import unpack_chars


class Target:
    def __init__(self, word_bits=36, chars_per_word=5, logical_true=-1):
        self.word_bits = word_bits
        self.chars_per_word = chars_per_word
        self.logical_true = logical_true
        self.mask = (1 << word_bits) - 1
        self.sign = 1 << (word_bits - 1)

    def wrap(self, v: int) -> int:
        """Reduce an integer to a signed word value (PDP-10: 2's-complement, 36 bits)."""
        v &= self.mask
        return v - (1 << self.word_bits) if v & self.sign else v

    def truthy(self, v) -> bool:
        """FORTRAN-10 logical: .TRUE. iff the sign is negative (.TRUE.=-1, .FALSE.=0)."""
        if isinstance(v, bool):
            return v
        return v < 0

    def pack(self, s: str) -> int:
        """Pack chars into one word (left-justified, blank-padded), as a signed word."""
        return self.wrap(pack5(s))

    def unpack(self, w: int, n=None) -> str:
        return unpack_chars(w, n if n is not None else self.chars_per_word)


PDP10 = Target()          # the default (and only shipped) target: 36-bit + SIXBIT/A5
