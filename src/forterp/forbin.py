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
class Dec10FloatError(Exception):
    """A float with no DEC-10 single-precision representation: inf/nan, or a magnitude
    outside the excess-128 exponent range. FOROTS reports a floating-overflow; we raise
    this rather than silently wrapping the exponent (corruption) or leaking a bare Python
    OverflowError/ValueError out of the codec."""


def double_to_dec10(x: float) -> int:
    """Encode a Python float as a 36-bit DEC-10 single-precision word.
    1.0 -> 0o201400000000, matching the documented PDP-10 representation."""
    if x == 0.0:
        return 0
    if not math.isfinite(x):  # inf / nan have no DEC-10 representation
        raise Dec10FloatError(f"cannot encode {x!r} as a DEC-10 single")
    neg = x < 0
    m, e = math.frexp(abs(x))  # abs(x) = m * 2**e, 0.5 <= m < 1.0
    frac = int(round(m * (1 << 27)))
    if frac > MASK27:  # rounding carried into 1.0
        frac >>= 1
        e += 1
    if not (-128 <= e <= 127):  # the excess-128 exponent field is 8 bits -> e in [-128,127]
        raise Dec10FloatError(f"{x!r} is out of DEC-10 single-precision range")
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
    if pos >= len(words):  # truncated buffer: a clean ValueError, not a raw IndexError
        raise ValueError(f"truncated binary record: no START LSCW at word {pos}")
    start = words[pos] & MASK36
    if (start >> 27) != START:
        raise ValueError(f"expected START LSCW at {pos}, got {start:012o}")
    cnt = start & MASK27  # words following START up to+incl END
    data = [w & MASK36 for w in words[pos + 1 : pos + cnt]]  # cnt-1 data + drop END
    return data, pos + 1 + cnt


# ---- sequential framing (START + data + per-block CONTINUE + END) --------------
# Manual D.5.2 (p. D-7/D-8): a sequential binary file is a word stream divided into
# 128-word disk blocks. A record is written as one or more segments split at each
# block boundary it crosses. START (001) opens the record; a CONTINUE (002) sits at
# every 128-word boundary the record spans; END (003) closes it. A START/CONTINUE
# count is the length of *its* segment (the control word + the data words up to the
# next control word); the END count is the whole record's length including all LSCWs.
# Validated against the manual's worked example (record 2 starts at word 0o146 with
# START count 0o32, then a CONTINUE at the 0o200 boundary with count 0o114).
SEQ_BLOCK = 0o200  # 128 words per disk block


def encode_sequential(records, block: int = SEQ_BLOCK) -> list:
    """Frame records as a FOROTS *sequential* binary word stream, inserting a CONTINUE
    LSCW at each `block`-word boundary a record crosses (unlike `encode_record`, which is
    the random-access short form with no CONTINUE). The block boundary is absolute from
    the start of the stream, so framing depends on every preceding record's length."""
    out: list = []
    for rec in records:
        data = [w & MASK36 for w in rec]
        rec_start = len(out)
        ctrl = [len(out)]  # indices of this record's START/CONTINUE words
        out.append(0)  # START placeholder
        for w in data:
            if len(out) % block == 0:  # crossing a block boundary mid-record -> CONTINUE
                ctrl.append(len(out))
                out.append(0)
            out.append(w)
        if len(out) % block == 0:  # the END word itself would land on a boundary
            ctrl.append(len(out))
            out.append(0)
        end_idx = len(out)
        out.append((END << 27) | ((end_idx - rec_start + 1) & MASK27))  # total incl. LSCWs
        bounds = ctrl + [end_idx]
        for k, ci in enumerate(ctrl):  # each START/CONTINUE counts its own segment length
            seg = bounds[k + 1] - ci
            out[ci] = ((START if k == 0 else CONTINUE) << 27) | (seg & MASK27)
    return out


def decode_sequential(words) -> list:
    """Parse a FOROTS sequential binary word stream (`encode_sequential`'s inverse) into a
    list of records, each a list of data words. Follows the LSCW chain START -> CONTINUE*
    -> END per record; the per-block CONTINUE words drop out."""
    records: list = []
    pos, n = 0, len(words)
    while pos < n:
        if (words[pos] >> 27) != START:
            raise ValueError(f"expected START LSCW at {pos}, got {words[pos] & MASK36:012o}")
        cnt = words[pos] & MASK27
        data = [w & MASK36 for w in words[pos + 1 : pos + cnt]]  # cnt-1 data words
        i = pos + cnt
        while True:
            if i >= n:
                raise ValueError(f"truncated sequential record: no END after word {pos}")
            code, cnt = words[i] >> 27, words[i] & MASK27
            if code == CONTINUE:
                data += [w & MASK36 for w in words[i + 1 : i + cnt]]
                i += cnt
            elif code == END:
                i += 1
                break
            else:
                raise ValueError(f"expected CONTINUE/END at {i}, got {words[i] & MASK36:012o}")
        records.append(data)
        pos = i
    return records


# ---- core-dump byte packing (36-bit words <-> bytes, the interchange form) -----
# A PDP-10 disk file is a stream of 36-bit words; to hold it in an 8-bit-byte host file
# the universal convention is "core-dump" mode: each word -> 5 bytes, the 36 data bits
# left-justified in 40 (low 4 bits of the 5th byte zero). This is what SIMH tapes and the
# DEC file-transfer tools use, so a file we write is the real word stream a PDP-10 stored.
def pack_core_dump(words) -> bytes:
    """Pack 36-bit words into bytes, 5 bytes/word, core-dump (left-justified) order."""
    out = bytearray()
    for word in words:
        w = word & MASK36
        out += bytes(
            ((w >> 28) & 0xFF, (w >> 20) & 0xFF, (w >> 12) & 0xFF, (w >> 4) & 0xFF, (w & 0xF) << 4)
        )
    return bytes(out)


def unpack_core_dump(data: bytes) -> list:
    """Unpack core-dump bytes back to 36-bit words (`pack_core_dump`'s inverse)."""
    if len(data) % 5:
        raise ValueError(f"core-dump byte stream not a multiple of 5 bytes: {len(data)}")
    words = []
    for i in range(0, len(data), 5):
        b0, b1, b2, b3, b4 = data[i : i + 5]
        words.append((b0 << 28) | (b1 << 20) | (b2 << 12) | (b3 << 4) | (b4 >> 4))
    return words


def encode_binary_file(records) -> bytes:
    """A whole FOROTS sequential binary file as host bytes: LSCW-framed words, core-dumped."""
    return pack_core_dump(encode_sequential(records))


def decode_binary_file(data: bytes) -> list:
    """Parse a FOROTS sequential binary file (host bytes) back into records of data words."""
    return decode_sequential(unpack_core_dump(data))
