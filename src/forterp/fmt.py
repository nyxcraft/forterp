"""A FORTRAN-10 V5 FORMAT engine: parse a FORMAT spec and render an output list,
or parse an input record.

Edit descriptors supported (V5 Ch13, Table 13-1):
  Iw, Ow (octal), Lw (logical), Aw / Rw (alphanumeric), Fw.d, Ew.d, Dw.d, Gw.d,
  nX, Tw (tab), nP (scale factor), kHs and '...' literals, / record delimiter,
  $ carriage-return suppression, and (group) repeats.  Bare descriptors (no
  width) take their V5 default widths (13.2.6, KI10/KL10): I15, O15, L15, A5,
  F15.7, E15.7, D25.18, G15.7, R5.
"""

from __future__ import annotations

import math

from forterp.target import NATIVE

MASK36 = (1 << 36) - 1


def unpack_chars(word, n):
    """Unpack up to n leading characters from a packed-ASCII word -- the PDP-10 layout:
    five 7-bit characters, char 0 in the high bits of a 36-bit word."""
    if isinstance(word, str):
        return word[:n] if n else word
    word_bits, bits, per_word, ascii_mask = 36, 7, 5, 0x7F
    u = int(word) & MASK36
    out = []
    for k in range(min(n, per_word) if n else per_word):
        c = (u >> (word_bits - bits * (k + 1))) & ascii_mask  # char k, high-justified
        out.append(chr(c) if c else " ")
    return "".join(out)


# ---- format spec parsing ---------------------------------------------------
class Item:
    __slots__ = ("kind", "a", "b", "e")

    def __init__(self, kind, a=None, b=None, e=None):
        self.kind, self.a, self.b, self.e = kind, a, b, e  # e: Ew.dEe exponent digit count

    def __repr__(self):
        return f"<{self.kind} {self.a} {self.b} {self.e}>"


class _Fmt(list):
    """A parsed FORMAT: the flat item list plus `rev`, the index at which reversion
    restarts (the start of the LAST top-level paren group, or 0 if none) -- V5/F66
    7.2.3.4 / X3.9-1966 §7.2.3.4."""

    rev = 0


def parse_format(spec: str):
    i = spec.find("(")
    j = spec.rfind(")")
    inner = spec[i + 1 : j] if (i >= 0 and j > i) else spec
    items, _, rev = _parse_seq(inner, 0)
    fmt = _Fmt(items)
    fmt.rev = rev
    return fmt


def _scan_string_literal(s, p):
    """Read a '...' literal whose opening quote is at s[p]; '' is an escaped apostrophe.
    Returns (the decoded text, the index past the closing quote)."""
    n = len(s)
    p += 1  # past the opening quote
    buf = []
    while p < n:
        if s[p] == "'":
            if p + 1 < n and s[p + 1] == "'":  # escaped '' -> one apostrophe
                buf.append("'")
                p += 2
                continue
            p += 1  # closing quote
            break
        buf.append(s[p])
        p += 1
    return "".join(buf), p


def _scan_width_decimals(s, p):
    """Read a data descriptor's optional width and optional `.decimals` starting at s[p].
    Returns (width, has_width, decimals-or-None, next index)."""
    n = len(s)
    w = 0
    has_w = False
    while p < n and s[p].isdigit():
        w = w * 10 + int(s[p])
        has_w = True
        p += 1
    d = None
    if p < n and s[p] == ".":
        p += 1
        d = 0
        while p < n and s[p].isdigit():
            d = d * 10 + int(s[p])
            p += 1
    return w, has_w, d, p


def _parse_seq(s, p, depth=0):
    items = []
    rev = 0  # last top-level group start (depth 0)
    n = len(s)
    while p < n:
        c = s[p]
        if c in " ,":
            p += 1
            continue
        if c == "/":
            items.append(Item("/"))
            p += 1
            continue
        if c == "$":
            items.append(Item("$"))
            p += 1
            continue
        if c == ")":
            return items, p + 1, rev
        if c == "'":
            text, p = _scan_string_literal(s, p)
            items.append(Item("lit", text))
            continue
        # optional sign (only meaningful as part of a scale factor nP)
        neg = False
        if c in "+-":
            neg = c == "-"
            p += 1
        # optional leading integer: a repeat count, or the n of an nP scale factor
        rep = 0
        while p < n and s[p].isdigit():
            rep = rep * 10 + int(s[p])
            p += 1
        if p < n and s[p] in "pP":  # scale factor:  [sign] n P
            p += 1
            items.append(Item("P", -rep if neg else rep))
            continue
        # a bare number with no descriptor letter or group after it counts as a repeat of 1
        at_descriptor = p < n and (s[p].isalpha() or s[p] == "(")
        if rep == 0 and not at_descriptor:
            rep = 1
        if p < n and s[p] == "(":  # group repeat
            grp = len(items)  # where this group's expansion begins
            sub, p, _ = _parse_seq(s, p + 1, depth + 1)
            for _ in range(max(rep, 1)):
                items.extend(sub)
            if depth == 0:  # F66 7.2.3.4: revert to last top-level group
                rev = grp
            continue
        if p >= n:
            break
        letter = s[p].upper()
        p += 1
        if letter == "H":  # nH literal begins immediately after the H
            text = s[p : p + rep]
            p += rep
            items.append(Item("lit", text))
            continue
        if letter == "S":  # sign control (13.5.6): SP = plus on, SS = plus off, S = default
            if p < n and s[p] in "Pp":
                p += 1
                items.append(Item("SP"))
            elif p < n and s[p] in "Ss":
                p += 1
                items.append(Item("SS"))
            else:
                items.append(Item("S"))
            continue
        if letter == "T" and p < n and s[p] in "LRlr":  # TL/TR relative tab (13.5.4)
            sub = s[p].upper()
            p += 1
            w2, _hw, _d, p = _scan_width_decimals(s, p)
            items.append(Item("T" + sub, w2 or 1))
            continue
        w, has_w, d, p = _scan_width_decimals(s, p)
        # Ew.dEe / Gw.dEe / Dw.dEe: an explicit exponent-digit count follows the decimals
        # (X3.9-1978 13.5.9). The marker letter abuts the decimals (no separator).
        ew = None
        if letter in "EGD" and p + 1 < n and s[p] in "EeDd" and s[p + 1].isdigit():
            p += 1
            ew = 0
            while p < n and s[p].isdigit():
                ew = ew * 10 + int(s[p])
                p += 1
        count = max(rep, 1)
        if letter == "X":  # nX = (rep) spaces
            items.append(Item("X", rep if rep else (w or 1)))
            continue
        for _ in range(count):
            items.append(Item(letter, w if has_w else None, d, ew))
    return items, p, rev


# ---- output ----------------------------------------------------------------
_DATA_DESCRIPTORS = ("A", "I", "G", "F", "E", "D", "O", "L", "R")

# V5 13.2.6 bare-descriptor default field widths (KI10/KL10): (w, d).
_DEFAULTS = {
    "A": (5, None),
    "R": (5, None),
    "I": (15, None),
    "O": (15, None),
    "L": (15, None),
    "F": (15, 7),
    "E": (15, 7),
    "D": (25, 18),
    "G": (15, 7),
}


class _Record:
    """One output record being built, with a write cursor so Tw can reposition
    (and overwrite) and nX can advance.  Tabbing past the end pads with blanks."""

    __slots__ = ("chars", "pos")

    def __init__(self):
        self.chars = []
        self.pos = 0

    def emit(self, s):
        for ch in s:
            while self.pos > len(self.chars):  # Tw left a gap -> blank-fill
                self.chars.append(" ")
            if self.pos < len(self.chars):
                self.chars[self.pos] = ch
            else:
                self.chars.append(ch)
            self.pos += 1

    def tab(self, col):  # Tw: 1-based record column
        self.pos = max(0, col - 1)

    def text(self):
        return "".join(self.chars)


def render(items, values, target=NATIVE):
    """Render an output record list. Returns (text, suppress_newline).

    Implements V5 FORMAT control (13.2.2/13.2.10): when the I/O list outlasts the
    descriptors, the format is re-scanned -- a new record (\\n) is started and the
    descriptors repeat (FORMAT reversion); when the list is exhausted mid-format,
    output terminates at that data descriptor (no zero padding). Records are joined
    with \\n (the first record's leading char is carriage control, applied later).
    """
    records = []
    rec = _Record()
    vi = 0
    suppress = False
    scale = 0  # nP scale factor (holds until reset, 13.2.4)
    plus = False  # SP/SS sign control: force a + on non-negative numerics (holds until reset)
    n = len(values)
    rev = getattr(items, "rev", 0)  # reversion restart: last top-level group (F66 7.2.3.4)
    start = 0  # first pass scans the whole format
    while True:
        pass_start = vi
        stop = False
        for it in items[start:]:
            k = it.kind
            if k == "lit":
                rec.emit(it.a)
            elif k == "X":
                rec.emit(" " * (it.a or 1))
            elif k == "T":
                rec.tab(it.a or 1)
            elif k == "TL":  # tab left (13.5.4): back up, not past column 1
                rec.pos = max(0, rec.pos - (it.a or 1))
            elif k == "TR":  # tab right: advance (a later emit blank-fills the gap)
                rec.pos += it.a or 1
            elif k == "P":
                scale = it.a or 0
            elif k in ("SP", "SS", "S"):  # sign control: SP forces + on non-negatives (13.5.6)
                plus = k == "SP"
            elif k == "/":
                records.append(rec.text())
                rec = _Record()
            elif k == "$":
                suppress = True
            elif k == ":":  # colon: terminate format control if the I/O list is exhausted (13.3)
                if vi >= n:
                    stop = True
                    break
            elif k in _DATA_DESCRIPTORS:
                if vi >= n:  # I/O list exhausted -> terminate record
                    stop = True
                    break
                v = values[vi]
                vi += 1
                rec.emit(_render_one(k, it, v, scale, target, plus))
        if stop or vi >= n or vi == pass_start:
            break
        records.append(rec.text())
        rec = _Record()  # reversion: new record
        start = rev  # ... restart at last top-level group
    records.append(rec.text())
    return "\n".join(records), suppress


def _render_one(k, it, v, scale, target=NATIVE, plus=False):
    """Render one value under data descriptor `k` (with the current scale factor and, when
    SP is active, a forced + on non-negative numerics)."""
    dw, dd = _DEFAULTS[k]
    w = it.a if it.a is not None else dw
    d = it.b if it.b is not None else dd
    if k == "A":
        # F77 §13.5.11: a widthless A writes the list item's own length (a CHARACTER value is a
        # Python str), so 'X' takes one column -- not the V5 default width (5). A Hollerith word
        # (the F66/FORTRAN-10 model) is not a str, so it keeps the default-width behaviour.
        if it.a is None and isinstance(v, str):
            return v
        return _afmt(v, w, target)
    if k == "R":
        return _rfmt(v, w, target)
    if k == "I":
        return _ifmt(int(v), w, d, plus)
    if k == "O":
        return _ofmt(int(v), w, target)
    if k == "L":
        return " " * (max(w, 1) - 1) + ("T" if target.truthy(v) else "F")
    if k == "F":
        return _real(float(v) * (10.0**scale) if scale else float(v), w, d, plus)
    if k in ("E", "D"):
        return _efmt(float(v), w, d, k, scale, it.e, plus)
    if k == "G":
        if isinstance(v, float):
            return _gfmt(v, w, d, scale, it.e, plus)
        return _ifmt(int(v), w)  # G on integer -> I conversion (13.2.3)
    return ""


def _afmt(v, w, target=NATIVE):
    """A descriptor: w>=m -> m chars right-justified, blank-filled; w<m -> leftmost w."""
    s = v if isinstance(v, str) else target.unpack(v, w if w else target.chars_per_word)
    if w:
        s = s[-w:].rjust(w) if len(s) < w else s[:w]
    return s


def _rfmt(v, w, target=NATIVE):
    """R descriptor: like A, but w<m takes the RIGHTMOST w chars (vs A's leftmost)."""
    full = v if isinstance(v, str) else target.unpack(v, target.chars_per_word)
    w = w or target.chars_per_word
    return full.rjust(w) if w >= len(full) else full[-w:]


def _ifmt(iv, w, m=None, plus=False):
    iv = int(iv)
    digits = str(abs(iv))
    if m is not None and len(digits) < m:  # Iw.m: at least m digits, zero-filled (13.5.9.1)
        digits = digits.zfill(m)
    s = ("-" if iv < 0 else "+" if plus else "") + digits
    if w and len(s) > w:
        return "*" * w  # V5 Table 13-2: too wide -> asterisks
    return s.rjust(w) if w else " " + s


def _ofmt(iv, w, target=NATIVE):
    s = format(int(iv) & target.mask, "o")  # octal of the word's bit pattern (target width)
    if w and len(s) > w:
        return "*" * w
    return s.zfill(w) if w else s  # V5 Table 13-2: O is ZERO-padded


def _fit(s, w):
    if w and len(s) > w:
        return "*" * w  # V5: field too small -> asterisks
    return s.rjust(w) if w else s


def _real(v, w, d, plus=False):
    if d is None:
        s = repr(v)
    elif d == 0:
        s = f"{v:.0f}."  # FORTRAN Fw.0 keeps the decimal point
    else:
        s = f"{v:.{d}f}"
    if s[:1] == "-" and float(s) == 0.0:
        s = s[1:]  # a negative value that rounds to zero carries no minus sign (F editing)
    if plus and s[:1] != "-":  # SP: force a + on a non-negative value
        s = "+" + s
    return _fit(s, w)


def _efmt(v, w, d, letter="E", scale=0, exp_width=None, plus=False):
    """FORTRAN E/D scientific with optional scale factor (V5 13.2.4).

    0P: mantissa 0.ddd in [0.1,1.0), exponent adjusted. nP shifts the decimal
    point n places (n integer digits for n>0) and decreases the exponent by n;
    the value is unchanged. Reproduces the manual's E15.3-of-12.493 examples.

    `exp_width` is the Ew.dEe exponent-digit count (X3.9-1978 13.5.9): the exponent
    is shown with exactly that many digits and the letter is always kept."""
    import math

    if v == 0.0:
        frac = d if scale <= 0 else max(0, d - scale + 1)
        body = ("0." + "0" * frac) if frac > 0 else "0."
        ez = f"{letter}+{0:0{exp_width}d}" if exp_width else f"{letter}+00"
        return _fit(f"{'+' if plus else ''}{body}{ez}", w)
    sign = "-" if v < 0 else ("+" if plus else "")
    av = abs(v)
    e0 = math.floor(math.log10(av)) + 1  # av = m0 * 10^e0, m0 in [0.1,1)
    r = round(av, (d + 1) - e0)  # carry d+1 significant digits
    if r > 0:
        e0 = math.floor(math.log10(r)) + 1  # rounding may bump a decade
    frac = d if scale <= 0 else max(0, d - scale + 1)
    exp_shown = e0 - scale
    mant = r / (10.0**exp_shown)
    body = f"{mant:.{frac}f}"
    if frac == 0:
        body += "."
    es = "+" if exp_shown >= 0 else "-"
    aexp = abs(exp_shown)
    if exp_width:  # Ew.dEe: exactly exp_width exponent digits, letter always kept (13.5.9)
        exp = f"{letter}{es}{aexp:0{exp_width}d}"
    else:
        # FORTRAN reserves 4 columns for the exponent (E+dd). A 3-digit exponent does not fit,
        # so the letter is dropped and the sign + 3 digits are shown (0.1E+101 -> 0.1+101).
        exp = f"{letter}{es}{aexp:02d}" if aexp < 100 else f"{es}{aexp:03d}"
    full = f"{sign}{body}{exp}"
    if w and len(full) > w and body[:2] == "0.":
        full = f"{sign}{body[1:]}{exp}"  # drop the optional leading 0 to fit the field (13.5.9)
    return _fit(full, w)


def _gfmt(v, w, d, scale=0, exp_width=None, plus=False):
    """FORTRAN G (V5 Table 13-4): fixed-point F(w-4).x,4X when 0.1<=|v|<10**d,
    else scientific Ew.d. The decimals shrink as the magnitude grows."""
    import math

    av = abs(v)
    if av != 0.0 and (av < 0.1 or av >= 10.0**d):
        return _efmt(v, w, d, "E", scale, exp_width, plus)  # out of F-range -> E
    if av == 0.0:
        decimals = d - 1
    else:
        e = math.floor(math.log10(av))  # av in [10**e, 10**(e+1))
        decimals = max(0, min(d - 1 - e, d))
    val = v * (10.0**scale) if scale else v  # F-form scale: ext = int*10**n
    body = _real(val, 0, decimals, plus)  # F field, no width yet
    if not w:
        return body + "    "
    fw = w - 4  # leave 4 blanks for the E exp slot
    if len(body) > fw:
        return "*" * w
    return body.rjust(fw) + "    "


def _carriage_one(rec):
    """Honor FORTRAN carriage control (ASA/FOROTS) for ONE record: its first character
    selects vertical spacing, translated to terminal/printer motion as a PREFIX only --
    the record's own line break is the surrounding newline. Consecutive ' ' records are
    single-spaced, not double (FORTRAN-10 terminal output)."""
    if not rec:
        return ""  # empty record -> a blank line
    c = rec[0]
    if c == "+":
        return "\r" + rec[1:]  # overprint: return to column 0
    if c == "0":
        return "\n" + rec[1:]  # double space: one blank line before this one
    if c == "1":
        return "\f" + rec[1:]  # form feed: top of next page
    if c == " ":
        return rec[1:]  # single space: normal advance
    return rec  # no recognized control char -> keep it, advance


def apply_carriage(text):
    """Apply carriage control to every record in `text`. A single WRITE can emit several
    records -- via FORMAT reversion or a '/' separator -- and EACH carries its own control
    character in column 1, so the control must be honored per record, not just the first."""
    return "\n".join(_carriage_one(rec) for rec in text.split("\n"))


def apply_carriage_advance(text):
    """FORTRAN-10 / FOROTS *advance-before-print* carriage control for terminal output.

    Where apply_carriage (above) is newline-AFTER -- each record terminated by the
    surrounding '\\n', matching printer/file output and the F77/FCVS golden streams --
    FOROTS drives a terminal advance-BEFORE: the column-1 control character is a LEADING
    motion emitted before the record's text, and the record is NOT newline-terminated.
    The cursor is therefore left at the end of the text, so a following direct write
    (e.g. an OUTSTR) continues the same line, and the NEXT record's leading advance is
    what ends this one. Verified byte-for-byte against the original on TOPS-10/SIMH:
    ' AAA'/ ; STROUT('BBB') ; ' CCC' ; STROUT('DDD')  ->  a leading blank, then "AAA",
    "BBB", a blank, then "CCCDDD" (CCC and DDD merged onto one line).

    Controls: ' ' advance 1, '0' advance 2, '1' form-feed, '+' no advance (continue at the
    cursor / overprint), empty record (a bare '/') advance 1. No trailing newline is added."""
    out = []
    for rec in text.split("\n"):
        if not rec:
            out.append("\n")  # empty record (e.g. a trailing '/') -> one advance
            continue
        c = rec[0]
        if c == "+":
            out.append(rec[1:])  # no advance: continue at the cursor (terminal overprint)
        elif c == "0":
            out.append("\n\n" + rec[1:])  # double space
        elif c == "1":
            out.append("\f" + rec[1:])  # form feed
        elif c == " ":
            out.append("\n" + rec[1:])  # single space
        else:
            out.append("\n" + rec)  # no recognized control char -> default single advance
    return "".join(out)


# ---- input -----------------------------------------------------------------
class InputConversionError(Exception):
    """An illegal character in a numeric/logical input field (V5: a runtime I/O error,
    e.g. ?FRSIVF). The engine routes it to a READ's ERR= label, or -- absent ERR= --
    lets it halt the program, as real FORTRAN-10 does. An all-blank field is NOT this:
    blanks are zeros, so it reads as 0 (F66 7.2.3.6)."""


# Edit descriptors that consume one input field (and produce one value), in transfer order.
# A widthless A reads as many columns as the matching list item's declared length, so the
# caller may pass `a_widths` -- one width per field, popped here in lockstep.
_VALUE_KINDS = frozenset({"A", "R", "G", "I", "O", "F", "E", "D", "L"})


def read_values(items, line, target=NATIVE, free_form=False, character_type=False, a_widths=None):
    """Parse `line` per the format (F66 7.2.3); return a list of (kind, value) reads.

    By default (F66) every numeric/logical field is read by COLUMN: leading blanks are
    insignificant, embedded/trailing blanks are zeros (7.2.3.6(1)); an F/E/G/D field
    with no decimal point gets the implied decimal d digits from the right (7.2.3.6.2);
    a kP scale divides an exponent-free field (7.2.3.5.1). A widthless descriptor uses
    its V5 default width as the column width.

    With `free_form=True` (the FORTRAN-10 input extension), a WIDTHLESS descriptor
    (`I`, `G`, ...) instead reads one free-form, whitespace/comma/tab-delimited token --
    the idiom ADVENT-style tab-delimited databases depend on. Width'd fields are always
    read by column.

    An nH / '...' field reads its chars FROM the record and is mutated in place
    (7.2.3.8). A record shorter than a field supplies only the columns it has."""
    vals = []
    pos = 0
    scale = 0  # current P scale factor (F66 7.2.3.5)
    for it in items:
        k = it.kind
        # pop one width hint per value-producing field, keeping lockstep with the io-list
        aw = next(a_widths, None) if (a_widths is not None and k in _VALUE_KINDS) else None
        if k in ("A", "R"):
            if pos < len(line) and line[pos] == "\t":  # legacy tab field-separator
                pos += 1
            # widthless A on input: under the F77 CHARACTER model the field is the list item's
            # declared length (supplied by the caller as aw; defaults to one char when unknown);
            # the Hollerith model (F66/FORTRAN-10) fills a whole word.
            w = it.a or ((aw or 1) if character_type and k == "A" else target.chars_per_word)
            field = line[pos : pos + w].ljust(w)
            # F77 CHARACTER: the field is a str (the caller fits it to the var's declared
            # length). Otherwise it is Hollerith packed into a word (the F66/FORTRAN-10 model).
            vals.append((k, field if character_type else target.pack(field)))
            pos += w
        elif k == "G":
            chunk, pos, tok = _grab(it, line, pos, free_form)
            if tok:  # widthless [DEC] G in free-form mode: integer token (V5/ADVENT)
                vals.append(("I", _to_int(chunk, 10)))
            else:  # Gw.d reads as for F (7.2.3.6.2)
                vals.append(("F", _read_real(chunk, it.b if it.a is not None else None, scale)))
        elif k in ("I", "O"):
            chunk, pos, tok = _grab(it, line, pos, free_form)
            if not tok:  # column field: embedded/trailing blanks are zeros
                chunk = _blank_fill(chunk)
            vals.append((k, _to_int(chunk, 8 if k == "O" else 10)))
        elif k in ("F", "E", "D"):
            chunk, pos, _tok = _grab(it, line, pos, free_form)
            vals.append(("F", _read_real(chunk, it.b if it.a is not None else None, scale)))
        elif k == "L":
            chunk, pos, _tok = _grab(it, line, pos, free_form)
            # X3.9-1978 13.5.10 / F66 7.2.3.7: optional leading blanks, then an OPTIONAL decimal
            # point, then T or F (any trailing chars ignored) -- so ".TRUE." reads as true.
            c = chunk.lstrip()
            if c[:1] == ".":
                c = c[1:]
            vals.append(("L", target.from_bool(c[:1].upper() == "T")))
        elif k == "P":  # scale factor; holds until reset (7.2.3.5)
            scale = it.a or 0
        elif k == "lit":  # nH / '...' field: input chars replace the literal
            w = len(it.a)
            it.a = line[pos : pos + w].ljust(w)
            pos += w
        elif k == "X":
            pos += it.a or 1
        elif k == "T":  # tab to 1-based column
            pos = max(0, (it.a or 1) - 1)
    return vals


def _grab(it, line, pos, free_form):
    """Extract one field's raw text -> (chunk, newpos, is_token). A widthless descriptor
    in free-form mode reads the next whitespace/comma/tab token (is_token=True); any
    width'd field, or any field in F66 column mode, is a column slice (is_token=False) of
    the field width -- the V5 default width when the descriptor is widthless."""
    if it.a is None and free_form:
        tok, pos = _next_token(line, pos)
        return tok, pos, True
    if it.a is not None:  # explicit width: a record shorter than the field is blank-
        w = it.a  # extended (and blanks are zeros), F66 7.2.3 -- as the char fields ljust
        return line[pos : pos + w].ljust(w), pos + w, False
    w = _DEFAULTS[it.kind][0]  # widthless [DEC] descriptor: read only the columns present
    return line[pos : pos + w], pos + w, False


def _next_token(line, pos):
    """The next whitespace/comma-delimited token and the position after it."""
    n = len(line)
    while pos < n and line[pos] in " ,\t":
        pos += 1
    start = pos
    while pos < n and line[pos] not in " ,\t":
        pos += 1
    return line[start:pos], pos


def _to_int(s, base):
    """Parse an integer field/token. An all-blank field reads as zero (blanks-as-zero,
    F66 7.2.3.6); a real written into a base-10 integer field is truncated toward zero;
    any other non-numeric field is a runtime input error (V5 -> ERR= or halt)."""
    if not s:  # all-blank field (after blank-fill) -> zero
        return 0
    try:
        return int(s, base)
    except ValueError:
        if base == 10:
            try:
                v = float(s.replace("D", "E").replace("d", "e"))
            except ValueError:
                v = None
            if v is not None and math.isfinite(v):  # a real written into an int field
                return int(v)  # (reject inf: 1E400 is out of range, not a value)
        raise InputConversionError(f"illegal character in integer field {s!r}") from None


def _blank_fill(field):
    """F66 7.2.3.6(1) blank handling for a width'd numeric field: leading blanks are
    insignificant; embedded and trailing blanks are zeros (all-blank field -> "")."""
    return field.lstrip(" ").replace(" ", "0")


def _read_real(field, d, scale):
    """Convert a real input field (Fw.d / Ew.d / Dw.d / Gw.d). The D and E exponent
    letters are interchangeable; a field with no decimal point places it `d` digits
    from the right (implied decimal); a kP scale factor divides an exponent-free field
    by 10**k. An all-blank field reads as zero; any other unreadable field is a runtime
    input error (V5 -> ERR= or halt)."""
    s = _blank_fill(field).replace("D", "E").replace("d", "e")
    if not s or s in ("+", "-"):  # all-blank field -> zero (blanks-as-zero)
        return 0.0
    try:
        v = float(s)
    except ValueError:
        raise InputConversionError(f"illegal character in real field {field!r}") from None
    # NB: an overflowing field (e.g. BZ blanks extending the exponent) yields inf -- a
    # deliberate FORTRAN-10 divergence pinned by test_read_bz_blanks_extend_into_the_exponent.
    if d and "." not in field:  # implied decimal: rightmost d digits are fractional
        v /= 10.0**d
    if scale and not _has_exponent(field):  # external = internal * 10**scale
        v /= 10.0**scale
    return v


def _has_exponent(field):
    """True if a real input field carries its own exponent -- an E/D letter or a signed
    power after the mantissa -- which suspends the scale factor (F66 7.2.3.5.1(2))."""
    body = field.strip()
    if body[:1] in "+-":
        body = body[1:]
    return any(c in "eEdD+-" for c in body)
