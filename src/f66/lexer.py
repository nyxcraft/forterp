"""Tokenizer for FORTRAN-10 statement text (post source-reader).

Token kinds:
  ID      identifier / keyword            value = uppercased name
  INT     decimal integer literal         value = int
  OCTAL   "nnn octal literal              value = int
  REAL    real literal                    value = float
  STR     '...' character/Hollerith       value = str (unescaped)
  DOTOP   .AND. .OR. .NOT. .EQ. ...        value = '.AND.' etc (uppercased)
  LOGIC   .TRUE. / .FALSE.                value = True / False
  OP      operator / punctuation          value = the operator text

The dialect specifics this handles (all verified present/absent in the
Empire sources): symbolic relationals == # < > <= >= ; '^' for power (no '**');
octal "nnn ; ':' in array bounds ; '$' in FORMAT ; '' as an escaped quote.
"""

from __future__ import annotations

from dataclasses import dataclass

from f66.dialect import FORTRAN10


@dataclass
class Token:
    kind: str
    value: object
    col: int


class LexError(Exception):
    def __init__(self, msg, col, mnemonic="IAC"):
        super().__init__(msg)
        self.col = col
        self.mnemonic = mnemonic            # FORTRAN-10 App-F diagnostic mnemonic


DOTOPS = {
    ".AND.", ".OR.", ".NOT.", ".EQ.", ".NE.", ".LT.", ".LE.",
    ".GT.", ".GE.", ".EQV.", ".NEQV.", ".XOR.",
}

# multi-char operators, longest first
MULTI_OPS = ("==", "<=", ">=")
SINGLE_OPS = set("+-*/^()=,<>#:$&")   # '&' = alt-return label prefix (V5 3.2.8: $n or &n)

_OCTAL = set("01234567")
_DIGIT = set("0123456789")


def _read_string(s: str, i: int):
    """Read a '...'-delimited literal starting at the opening quote (s[i])."""
    n = len(s)
    i += 1  # past opening quote
    buf = []
    while i < n:
        c = s[i]
        if c == "'":
            if i + 1 < n and s[i + 1] == "'":
                buf.append("'")
                i += 2
                continue
            return "".join(buf), i + 1
        buf.append(c)
        i += 1
    raise LexError("NO CLOSING QUOTE IN LITERAL", i, "CQL")


def _read_number(s: str, i: int):
    """Read an int or real literal starting at s[i] (a digit or '.')."""
    n = len(s)
    start = i
    is_real = False
    while i < n and s[i] in _DIGIT:
        i += 1
    if i < n and s[i] == ".":
        # A '.' after digits is a decimal point UNLESS it begins a dotted operator:
        # FORTRAN parses 1000.EQ.2 as 1000 .EQ. 2, not 1000.<exponent> (.EQ. starts
        # with 'E', which would otherwise look like an exponent letter).
        if _match_dot(s, i) is not None:
            pass                                  # dotted operator -> the integer ends here
        else:
            nxt = s[i + 1] if i + 1 < n else ""
            if nxt.isalpha():
                if nxt in "eEdD":                 # exponent letter -> real; consume the '.'
                    is_real = True
                    i += 1
                # else: a stray letter -> leave the dot for the operator scanner
            else:
                is_real = True                    # decimal point
                i += 1
                while i < n and s[i] in _DIGIT:
                    i += 1
    # exponent
    if i < n and s[i] in "eEdD":
        j = i + 1
        if j < n and s[j] in "+-":
            j += 1
        if j < n and s[j] in _DIGIT:
            is_real = True
            i = j
            while i < n and s[i] in _DIGIT:
                i += 1
    text = s[start:i]
    if is_real:
        return Token("REAL", float(text.replace("d", "e").replace("D", "E")), start), i
    # Hollerith nH literal: an integer immediately followed by H (no space) is a
    # count of the following raw characters, e.g. 5HHELLO -> "HELLO". Same token as
    # an apostrophe string. (A space before H, as in "DO 5 H", is not Hollerith.)
    if i < n and s[i] in "Hh":                 # nH or nh -- FORTRAN is case-insensitive
        count = int(text)
        return Token("STR", s[i + 1:i + 1 + count], start), i + 1 + count
    return Token("INT", int(text), start), i


def tokenize(s: str, dialect=FORTRAN10) -> list[Token]:
    toks: list[Token] = []
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        if c in " \t":
            i += 1
            continue
        if c == "'":
            # A "'" right after a NUMERIC literal is the random-access record
            # separator READ(u'r), not a string. Restricted to INT/OCTAL: an ID can
            # be a FORMAT descriptor (I3'TEXT') or a keyword (STOP 'msg'), where the
            # "'" really does start a string. Variable units use the u#r form instead.
            prev = toks[-1] if toks else None
            if (prev is not None and prev.kind in ("INT", "OCTAL")
                    and dialect.random_access_quote):
                toks.append(Token("OP", "'", i)); i += 1
                continue
            val, i2 = _read_string(s, i)
            toks.append(Token("STR", val, i))
            i = i2
            continue
        if c == '"' and dialect.octal_quote:
            j = i + 1
            while j < n and s[j] in _OCTAL:
                j += 1
            if j == i + 1:
                raise LexError('octal literal with no digits after "', i)
            toks.append(Token("OCTAL", int(s[i + 1:j], 8), i))
            i = j
            continue
        if c in _DIGIT:
            tok, i = _read_number(s, i)
            toks.append(tok)
            continue
        if c == ".":
            # dotted operator / logical constant, else a number like .5
            m = _match_dot(s, i)
            if m is not None:
                word, i2 = m
                if word == ".TRUE.":
                    toks.append(Token("LOGIC", True, i))
                elif word == ".FALSE.":
                    toks.append(Token("LOGIC", False, i))
                else:
                    toks.append(Token("DOTOP", word, i))
                i = i2
                continue
            if i + 1 < n and s[i + 1] in _DIGIT:
                tok, i = _read_number(s, i)
                toks.append(tok)
                continue
            raise LexError("ILLEGAL ASCII CHARACTER '.' IN SOURCE", i, "IAC")
        if c.isalpha():
            j = i + 1
            while j < n and (s[j].isalnum() or s[j] == "_"):
                j += 1
            toks.append(Token("ID", s[i:j].upper(), i))
            i = j
            continue
        # operators
        two = s[i:i + 2]
        if two == "**":                       # standard FORTRAN power == DEC's '^'
            toks.append(Token("OP", "^", i))
            i += 2
            continue
        if two in MULTI_OPS:
            toks.append(Token("OP", two, i))
            i += 2
            continue
        if c in SINGLE_OPS:
            toks.append(Token("OP", c, i))
            i += 1
            continue
        raise LexError(f"ILLEGAL ASCII CHARACTER {c!r} IN SOURCE", i, "IAC")
    return toks


def _match_dot(s: str, i: int):
    """If s[i:] begins with a dotted word like .AND./.TRUE., return (WORD, end)."""
    n = len(s)
    j = i + 1
    while j < n and s[j].isalpha():
        j += 1
    if j < n and s[j] == "." and j > i + 1:
        word = s[i:j + 1].upper()
        if word in DOTOPS or word in (".TRUE.", ".FALSE."):
            return word, j + 1
    return None
