"""FOROTS binary (unformatted) record format -- FORTRAN-10 V5 manual Appendix D.5.2.

A FORTRAN binary record is a stream of 36-bit words framed by Logical-Segment
Control Words (LSCW). One LSCW is a single 36-bit word:

    bits 0-8   (top 9 bits)   code:  001 START, 002 CONTINUE, 003 END
    bits 9-35  (low 27 bits)  word count

Confirmed against the actual FOROTS source (forio.mac, FORTRAN-10 V7, trailing-edge
PDP-10 archive): the reader does `LDB T2,[POINT 9,T1,8]` (extract bits 0-8) then
`CAIE T2,1`/`CAIN T2,3`/`CAIE T2,2` (START/END/CONTINUE), and `TLZ T1,777000`
(clear bits 0-8) to leave the count -- exactly `word>>27` / `word & MASK27` here.

    START   001 + number of words following it up to AND INCLUDING the END LSCW
    CONTINUE 002 at each 128-word disk-block boundary a segment crosses (seq. only)
    END     003 + total number of words in the record, INCLUDING both LSCWs

Random-access ('RANDOM'/'RANDIN') records use only START+END (fixed length, no
CONTINUE). Validated byte-for-byte against the manual's D-6 example: the record
  WRITE(1'1) (I, J=1,100)   with I=5
is  001000000145 , 100*000000000005 , 003000000146  (octal).

Data words are DECsystem-10 machine words (manual 13.x): INTEGER = 36-bit two's
complement; REAL = DEC-10 single float (sign / excess-128 exponent / 27-bit
fraction, the whole word two's-complemented when negative). DOUBLE/COMPLEX = two
such words. This is the on-the-wire form; in memory we keep Python int/float, so
encode/decode happens only at the binary-I/O boundary (like packed ASCII).
"""

from __future__ import annotations

import math

MASK36 = (1 << 36) - 1
MASK27 = (1 << 27) - 1
START, CONTINUE, END = 0o1, 0o2, 0o3


# ---- DECsystem-10 single-precision floating point -----------------------------
def double_to_dec10(x: float) -> int:
    """Encode a Python float as a 36-bit DEC-10 single-precision word.
    1.0 -> 0o201400000000, matching the documented PDP-10 representation."""
    if x == 0.0:
        return 0
    neg = x < 0
    m, e = math.frexp(abs(x))  # abs(x) = m * 2**e, 0.5 <= m < 1.0
    frac = int(round(m * (1 << 27)))
    if frac > MASK27:  # rounding carried into 1.0
        frac >>= 1
        e += 1
    word = (((e + 128) & 0o377) << 27) | (frac & MASK27)  # bit0=0 (positive)
    return (-word) & MASK36 if neg else word  # negate the whole word


def dec10_to_double(word: int) -> float:
    """Decode a 36-bit DEC-10 single-precision word to a Python float."""
    word &= MASK36
    if word == 0:
        return 0.0
    neg = (word >> 35) & 1
    if neg:
        word = (-word) & MASK36  # undo two's complement -> magnitude form
    expfield = (word >> 27) & 0o377
    frac = (word & MASK27) / (1 << 27)
    val = math.ldexp(frac, expfield - 128)
    return -val if neg else val


# ---- LSCW record framing (random / short form: START + data + END) ------------
def encode_record(data_words) -> list:
    """Frame a list of 36-bit data words as a FOROTS binary record."""
    data = [w & MASK36 for w in data_words]
    n = len(data)
    start = (START << 27) | ((n + 1) & MASK27)  # words following START thru END
    end = (END << 27) | ((n + 2) & MASK27)  # total words incl. both LSCWs
    return [start] + data + [end]


def decode_record(words, pos: int = 0):
    """Read one record whose START LSCW is at words[pos]. Returns (data_words,
    next_pos). Raises ValueError if words[pos] is not a START LSCW."""
    start = words[pos] & MASK36
    if (start >> 27) != START:
        raise ValueError(f"expected START LSCW at {pos}, got {start:012o}")
    cnt = start & MASK27  # words following START up to+incl END
    data = [w & MASK36 for w in words[pos + 1 : pos + cnt]]  # cnt-1 data + drop END
    return data, pos + 1 + cnt
