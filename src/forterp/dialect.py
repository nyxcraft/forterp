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
    dec_operators: bool = False  # operators beyond ANSI X3.9-1966 §6.1: the symbolic
    # relationals (== # < > <= >=, vs .EQ./.NE./.LT./.LE./.GT./.GE.), the extended logicals
    # (.XOR./.EQV./.NEQV., vs .NOT./.AND./.OR.), and `^` as a power operator (`**` is ANSI).
    stmt_separator: bool = False  # `;` multi-statement lines (F66 is one statement per line)
    array_lower_bounds: bool = False  # DIMENSION A(lo:hi) explicit lower bounds (F66 is 1..n)
    parameter_stmt: bool = False  # the PARAMETER statement (added in F77; not in ANSI F66)
    star_sizes: bool = False  # INTEGER*4 / REAL*8 byte-size type specifiers (DEC/F77)
    alt_return: bool = False  # alternate-return actual args in CALL ($n/&n/*n) (F77/DEC)
    block_if: bool = False  # block IF...THEN / ELSE IF / ELSE / END IF (F77; also FORTRAN-10 V5)
    do_while: bool = False  # DO WHILE (cond) / END DO (DEC/F90 ext; NOT in ANSI X3.9-1978)
    save_stmt: bool = False  # the SAVE statement (F77; a no-op here -- locals are already static)


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
    dec_operators=True,
    stmt_separator=True,
    array_lower_bounds=True,
    parameter_stmt=True,
    star_sizes=True,
    alt_return=True,
    block_if=True,  # block IF is a FORTRAN-10 V5 construct
    do_while=True,  # DEC FORTRAN-10 has DO WHILE
    save_stmt=True,
)
# ANSI X3.9-1978 (FORTRAN 77): the standard between F66 and the DEC superset. Reuses the
# knobs F77 standardized; DEC-only extensions (octal `"`, tab format, free-form input, TYPE/
# ACCEPT, ENCODE/DECODE, symbolic == operators, `;`, DO WHILE) stay off. CHARACTER and the
# full F77 I/O set are not here yet (planned); this is the control-flow + declaration subset.
F77 = Dialect(
    apostrophe_string=True,  # CHARACTER/Hollerith apostrophe constants
    implicit_stmt=True,
    expr_subscripts=True,
    array_lower_bounds=True,
    parameter_stmt=True,
    alt_return=True,
    mixed_complex_assign=True,
    dec_intrinsics=True,  # the F77 generic intrinsic library (a superset is fine for now)
    block_if=True,
    save_stmt=True,
)

# CLI / front-end name -> dialect, so every caller resolves the same names in one place.
DIALECTS = {"f66": F66, "fortran10": FORTRAN10, "f77": F77}
