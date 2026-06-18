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

from f66.target import PDP10

MASK36 = (1 << 36) - 1


def unpack_chars(word, n):
    """Unpack up to n leading 7-bit characters from a packed-ASCII word."""
    if isinstance(word, str):
        return word[:n] if n else word
    u = int(word) & MASK36
    out = []
    for k in range(min(n, 5) if n else 5):
        c = (u >> (29 - 7 * k)) & 0x7F
        out.append(chr(c) if c else " ")
    return "".join(out)


# ---- format spec parsing ---------------------------------------------------
class Item:
    __slots__ = ("kind", "a", "b")
    def __init__(self, kind, a=None, b=None):
        self.kind, self.a, self.b = kind, a, b
    def __repr__(self):
        return f"<{self.kind} {self.a} {self.b}>"


class _Fmt(list):
    """A parsed FORMAT: the flat item list plus `rev`, the index at which reversion
    restarts (the start of the LAST top-level paren group, or 0 if none) -- V5/F66
    7.2.3.4 / X3.9-1966 §7.2.3.4."""
    rev = 0


def parse_format(spec: str):
    i = spec.find("(")
    j = spec.rfind(")")
    inner = spec[i + 1:j] if (i >= 0 and j > i) else spec
    items, _, rev = _parse_seq(inner, 0)
    fmt = _Fmt(items)
    fmt.rev = rev
    return fmt


def _parse_seq(s, p, depth=0):
    items = []
    rev = 0                                       # last top-level group start (depth 0)
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
            buf = []
            p += 1
            while p < n:
                if s[p] == "'":
                    if p + 1 < n and s[p + 1] == "'":
                        buf.append("'"); p += 2; continue
                    p += 1
                    break
                buf.append(s[p]); p += 1
            items.append(Item("lit", "".join(buf)))
            continue
        # optional sign (only meaningful as part of a scale factor nP)
        neg = False
        if c in "+-":
            neg = (c == "-")
            p += 1
        # optional leading integer: a repeat count, or the n of an nP scale factor
        rep = 0
        have_rep = False
        while p < n and s[p].isdigit():
            rep = rep * 10 + int(s[p]); have_rep = True; p += 1
        if p < n and s[p] in "pP":              # scale factor:  [sign] n P
            p += 1
            items.append(Item("P", -rep if neg else rep))
            continue
        if rep == 0 and not (p < n and (s[p].isalpha() or s[p] in "(")):
            rep = 1
        if p < n and s[p] == "(":               # group repeat
            grp = len(items)                     # where this group's expansion begins
            sub, p, _ = _parse_seq(s, p + 1, depth + 1)
            for _ in range(max(rep, 1)):
                items.extend(sub)
            if depth == 0:                       # F66 7.2.3.4: revert to last top-level group
                rev = grp
            continue
        if p >= n:
            break
        letter = s[p].upper(); p += 1
        w = 0
        has_w = False
        while p < n and s[p].isdigit():
            w = w * 10 + int(s[p]); has_w = True; p += 1
        d = None
        if p < n and s[p] == ".":
            p += 1
            d = 0
            while p < n and s[p].isdigit():
                d = d * 10 + int(s[p]); p += 1
        count = max(rep, 1)
        if letter == "X":                        # nX = (rep) spaces
            items.append(Item("X", rep if rep else (w or 1)))
            continue
        if letter == "H":                        # nH literal (rep chars)
            text = s[p:p + rep]; p += rep
            items.append(Item("lit", text))
            continue
        for _ in range(count):
            items.append(Item(letter, w if has_w else None, d))
    return items, p, rev


# ---- output ----------------------------------------------------------------
_DATA_DESCRIPTORS = ("A", "I", "G", "F", "E", "D", "O", "L", "R")

# V5 13.2.6 bare-descriptor default field widths (KI10/KL10): (w, d).
_DEFAULTS = {
    "A": (5, None), "R": (5, None), "I": (15, None), "O": (15, None),
    "L": (15, None), "F": (15, 7), "E": (15, 7), "D": (25, 18), "G": (15, 7),
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
            while self.pos > len(self.chars):       # Tw left a gap -> blank-fill
                self.chars.append(" ")
            if self.pos < len(self.chars):
                self.chars[self.pos] = ch
            else:
                self.chars.append(ch)
            self.pos += 1

    def tab(self, col):                              # Tw: 1-based record column
        self.pos = max(0, col - 1)

    def text(self):
        return "".join(self.chars)


def render(items, values, target=PDP10):
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
    scale = 0                       # nP scale factor (holds until reset, 13.2.4)
    n = len(values)
    rev = getattr(items, "rev", 0)  # reversion restart: last top-level group (F66 7.2.3.4)
    start = 0                       # first pass scans the whole format
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
            elif k == "P":
                scale = it.a or 0
            elif k == "/":
                records.append(rec.text()); rec = _Record()
            elif k == "$":
                suppress = True
            elif k in _DATA_DESCRIPTORS:
                if vi >= n:                # I/O list exhausted -> terminate record
                    stop = True
                    break
                v = values[vi]; vi += 1
                rec.emit(_render_one(k, it, v, scale, target))
        if stop or vi >= n or vi == pass_start:
            break
        records.append(rec.text()); rec = _Record()   # reversion: new record
        start = rev                                    # ... restart at last top-level group
    records.append(rec.text())
    return "\n".join(records), suppress


def _render_one(k, it, v, scale, target=PDP10):
    """Render one value under data descriptor `k` (with the current scale factor)."""
    dw, dd = _DEFAULTS[k]
    w = it.a if it.a is not None else dw
    d = it.b if it.b is not None else dd
    if k == "A":
        return _afmt(v, w, target)
    if k == "R":
        return _rfmt(v, w, target)
    if k == "I":
        return _ifmt(int(v), w)
    if k == "O":
        return _ofmt(int(v), w, target)
    if k == "L":
        return " " * (max(w, 1) - 1) + ("T" if target.truthy(v) else "F")
    if k == "F":
        return _real(float(v) * (10.0 ** scale) if scale else float(v), w, d)
    if k in ("E", "D"):
        return _efmt(float(v), w, d, k, scale)
    if k == "G":
        if isinstance(v, float):
            return _gfmt(v, w, d, scale)
        return _ifmt(int(v), w)            # G on integer -> I conversion (13.2.3)
    return ""


def _afmt(v, w, target=PDP10):
    """A descriptor: w>=m -> m chars right-justified, blank-filled; w<m -> leftmost w."""
    s = v if isinstance(v, str) else target.unpack(v, w if w else target.chars_per_word)
    if w:
        s = s[-w:].rjust(w) if len(s) < w else s[:w]
    return s


def _rfmt(v, w, target=PDP10):
    """R descriptor: like A, but w<m takes the RIGHTMOST w chars (vs A's leftmost)."""
    full = v if isinstance(v, str) else target.unpack(v, target.chars_per_word)
    w = w or target.chars_per_word
    return full.rjust(w) if w >= len(full) else full[-w:]


def _ifmt(iv, w):
    s = str(int(iv))
    if w and len(s) > w:
        return "*" * w                     # V5 Table 13-2: too wide -> asterisks
    return s.rjust(w) if w else " " + s


def _ofmt(iv, w, target=PDP10):
    s = format(int(iv) & target.mask, "o")  # octal of the word's bit pattern (target width)
    if w and len(s) > w:
        return "*" * w
    return s.zfill(w) if w else s          # V5 Table 13-2: O is ZERO-padded


def _fit(s, w):
    if w and len(s) > w:
        return "*" * w                     # V5: field too small -> asterisks
    return s.rjust(w) if w else s


def _real(v, w, d):
    if d is None:
        s = repr(v)
    elif d == 0:
        s = f"{v:.0f}."                    # FORTRAN Fw.0 keeps the decimal point
    else:
        s = f"{v:.{d}f}"
    return _fit(s, w)


def _efmt(v, w, d, letter="E", scale=0):
    """FORTRAN E/D scientific with optional scale factor (V5 13.2.4).

    0P: mantissa 0.ddd in [0.1,1.0), exponent adjusted. nP shifts the decimal
    point n places (n integer digits for n>0) and decreases the exponent by n;
    the value is unchanged. Reproduces the manual's E15.3-of-12.493 examples."""
    import math
    if v == 0.0:
        frac = d if scale <= 0 else max(0, d - scale + 1)
        body = ("0." + "0" * frac) if frac > 0 else "0."
        return _fit(f"{body}{letter}+00", w)
    sign = "-" if v < 0 else ""
    av = abs(v)
    e0 = math.floor(math.log10(av)) + 1               # av = m0 * 10^e0, m0 in [0.1,1)
    r = round(av, (d + 1) - e0)                        # carry d+1 significant digits
    if r > 0:
        e0 = math.floor(math.log10(r)) + 1             # rounding may bump a decade
    frac = d if scale <= 0 else max(0, d - scale + 1)
    exp_shown = e0 - scale
    mant = r / (10.0 ** exp_shown)
    body = f"{mant:.{frac}f}"
    if frac == 0:
        body += "."
    es = "+" if exp_shown >= 0 else "-"
    return _fit(f"{sign}{body}{letter}{es}{abs(exp_shown):02d}", w)


def _gfmt(v, w, d, scale=0):
    """FORTRAN G (V5 Table 13-4): fixed-point F(w-4).x,4X when 0.1<=|v|<10**d,
    else scientific Ew.d. The decimals shrink as the magnitude grows."""
    import math
    av = abs(v)
    if av != 0.0 and (av < 0.1 or av >= 10.0 ** d):
        return _efmt(v, w, d, "E", scale)              # out of F-range -> E
    if av == 0.0:
        decimals = d - 1
    else:
        e = math.floor(math.log10(av))                 # av in [10**e, 10**(e+1))
        decimals = max(0, min(d - 1 - e, d))
    val = v * (10.0 ** scale) if scale else v          # F-form scale: ext = int*10**n
    body = _real(val, 0, decimals)                     # F field, no width yet
    if not w:
        return body + "    "
    fw = w - 4                                          # leave 4 blanks for the E exp slot
    if len(body) > fw:
        return "*" * w
    return body.rjust(fw) + "    "


def apply_carriage(text):
    """Honor FORTRAN carriage control (ASA/FOROTS): the first character of a record
    selects vertical spacing. We translate it to terminal/printer motion as a PREFIX
    only -- the record's own line break is the trailing newline the caller appends.
    So consecutive ' ' (single-space) records are single-spaced, not double; this
    matches FORTRAN-10 terminal output (e.g. Adventure's multi-line room text)."""
    if not text:
        return ""                   # empty record -> a blank line (caller's trailing \n)
    c = text[0]
    if c == "+":
        return "\r" + text[1:]      # overprint: return to column 0
    if c == "0":
        return "\n" + text[1:]      # double space: one blank line before this one
    if c == "1":
        return "\f" + text[1:]      # form feed: top of next page
    if c == " ":
        return text[1:]             # single space: normal advance (the trailing \n)
    return text                     # no recognized control char -> keep it, advance


# ---- input -----------------------------------------------------------------
def read_values(items, line, target=PDP10):
    """Parse `line` per the format; return a list of (kind, value) reads."""
    vals = []
    pos = 0
    for it in items:
        if it.kind in ("A", "R"):
            if pos < len(line) and line[pos] == "\t":   # field separator from a prior
                pos += 1                                  # numeric field (tab-delimited data)
            w = it.a or target.chars_per_word
            chunk = line[pos:pos + w]
            pos += w
            vals.append((it.kind, target.pack(chunk.ljust(w))))
        elif it.kind in ("I", "G"):
            tok, pos = _next_token(line, pos)
            try:
                vals.append(("I", int(tok)))
            except ValueError:
                try:
                    vals.append(("I", int(float(tok))))
                except ValueError:
                    vals.append(("I", 0))
        elif it.kind == "O":
            tok, pos = _next_token(line, pos)
            try:
                vals.append(("O", int(tok, 8)))
            except ValueError:
                vals.append(("O", 0))
        elif it.kind == "L":
            w = it.a
            if w:
                chunk = line[pos:pos + w]; pos += w
            else:
                chunk, pos = _next_token(line, pos)
            t = chunk.lstrip()[:1].upper()             # first non-blank: T or F
            vals.append(("L", target.from_bool(t == "T")))
        elif it.kind in ("F", "E", "D"):
            tok, pos = _next_token(line, pos)
            try:
                vals.append(("F", float(tok)))
            except ValueError:
                vals.append(("F", 0.0))
        elif it.kind == "X":
            pos += it.a or 1
        elif it.kind == "T":                           # tab to 1-based column
            pos = max(0, (it.a or 1) - 1)
    return vals


def _next_token(line, pos):
    n = len(line)
    while pos < n and line[pos] in " ,\t":
        pos += 1
    start = pos
    while pos < n and line[pos] not in " ,\t":
        pos += 1
    return line[start:pos], pos
