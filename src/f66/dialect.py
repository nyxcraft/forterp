"""Front-end dialect config -- the parse-level knobs that distinguish DEC FORTRAN-10
from strict ANSI FORTRAN-66.

The lexer and source reader read a Dialect (threaded through tokenize / scan_file /
parse_units, default FORTRAN10) and gate their DEC extensions on it, so the front-end
is selectable in place -- a host program picks the dialect rather than shipping its
own lexer.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Dialect:
    octal_quote: bool = True           # "nnn  octal literal (DEC extension)
    random_access_quote: bool = True   # READ(u'r) random-access record separator (DEC ext)
    tab_format: bool = True            # DEC tab-format source lines (V5 2.2.2)
    inline_comment: bool = True        # trailing '!' comment (DEC ext; not ANSI F66)
    strict_cols: bool = False          # hard 72-col field (vs lenient sequence-field trim)


FORTRAN10 = Dialect()                  # DEC FORTRAN-10 V5 -- default + only shipped dialect
STRICT_F66 = Dialect(octal_quote=False, random_access_quote=False, tab_format=False,
                     inline_comment=False, strict_cols=True)
