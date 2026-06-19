"""Front-end dialect config -- the parse/read-level knobs that distinguish strict ANSI
FORTRAN-66 from the DEC FORTRAN-10 superset.

The lexer, source reader, and formatted-input reader read a Dialect (threaded through
tokenize / scan_file / parse_units / the engine, default F66) and gate their DEC
extensions on it. `F66` is the default -- this is an ANSI X3.9-1966 implementation, so
the standard is what you get unless you opt into the DEC extensions with `FORTRAN10`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Dialect:
    # All flags default to the ANSI X3.9-1966 (F66) setting; FORTRAN10 turns them on.
    # NB: cols 73-80 (the sequence field) are dropped by BOTH real dialects, so that is
    # NOT a dialect knob -- keeping shifted text past col 72 is a source-recovery concern,
    # see source.SourceOptions.
    octal_quote: bool = False  # "nnn  octal literal (DEC extension)
    random_access_quote: bool = False  # READ(u'r) random-access record separator (DEC)
    tab_format: bool = False  # DEC tab-format source lines (V5 2.2.2)
    inline_comment: bool = False  # trailing '!' comment (DEC ext; not ANSI F66)
    free_form_input: bool = False  # widthless numeric input fields read free-form (DEC)
    apostrophe_string: bool = False  # '...' string literal (F66 5.1.1.6: Hollerith nH only)
    implicit_stmt: bool = False  # IMPLICIT statement (F66: only the built-in I-N rule)
    expr_subscripts: bool = False  # general int exprs in subscripts/DO bounds (F66 5.1.3.3 /
    # 7.1.2.8 allow only c*v±k subscripts and constant/variable DO parameters)
    mixed_complex_assign: bool = False  # COMPLEX <-> int/real/double assignment (F66 Table 1
    # prohibits it -- COMPLEX may only be assigned to/from COMPLEX)
    extended_io: bool = False  # non-F66 I/O: TYPE/PRINT/ACCEPT/PUNCH, ENCODE/DECODE, unit-
    # less READ/WRITE/REREAD, list-directed `*`, and random-access (DEFINE FILE, FIND, u#r/
    # u'r). F66 has only READ/WRITE with a unit + the auxiliary BACKSPACE/REWIND/ENDFILE (§7.1.3)
    bare_format_width: bool = False  # widthless FORMAT descriptors I/F/A/... (F66 §7.2.3.1
    # requires an explicit width on every descriptor; DEC supplies V5 default widths)
    dec_intrinsics: bool = False  # the DEC/F77 extra library functions beyond F66 Tables 3
    # & 4 (TAN, NINT/ANINT, the DP DTAN.../degree TAND... families, LSH, MAX/MIN, ...). F66
    # exposes only the 55 standard functions; set this (e.g. Dialect(dec_intrinsics=True))
    # to opt into the DEC library under F66 without the rest of the FORTRAN10 superset.


F66 = Dialect()  # ANSI X3.9-1966 -- the default dialect
FORTRAN10 = Dialect(  # DEC FORTRAN-10 V5 superset: every extension on
    octal_quote=True,
    random_access_quote=True,
    tab_format=True,
    inline_comment=True,
    free_form_input=True,
    apostrophe_string=True,
    implicit_stmt=True,
    expr_subscripts=True,
    mixed_complex_assign=True,
    extended_io=True,
    bare_format_width=True,
    dec_intrinsics=True,
)
