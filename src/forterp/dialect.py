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
    # less READ/WRITE/REREAD, and random-access (DEFINE FILE, FIND, u#r/u'r). F66 has only
    # READ/WRITE with a unit + the auxiliary BACKSPACE/REWIND/ENDFILE (§7.1.3)
    list_directed_io: bool = False  # list-directed `*` READ/WRITE (standardized in F77 §12;
    # a DEC extension before that -- on under FORTRAN-10, and on its own for F77)
    bare_format_width: bool = False  # widthless FORMAT descriptors I/F/A/... (F66 §7.2.3.1
    # requires an explicit width on every descriptor; DEC supplies V5 default widths)
    f77_intrinsics: bool = False  # the ANSI X3.9-1978 intrinsic additions beyond F66 Tables 3
    # & 4: generic LOG/MAX/MIN, TAN/ASIN/ACOS/SINH/COSH, the D... double specifics, NINT/ANINT,
    # DPROD/DDIM, and the CHARACTER intrinsics (LEN/CHAR/ICHAR/INDEX, LGE/LGT/LLE/LLT). On for F77.
    dec_library: bool = False  # the DEC-only library beyond F77: the DEC intrinsics (LSH/ROT,
    # degree-argument trig TAND/SIND..., the DOUBLE COMPLEX helpers, FLOATR/DFLOAT/TIM2GO), the
    # DEC subprograms (RAN/DATE/ERRSET/...), and the DEC terminal free-CR-LF wrap. FORTRAN10 only.
    uuo_library: bool = False  # the TOPS-10 monitor UUOs callable from FORTRAN (OUTSTR/OUTCHR/
    # MSTIME/SLEEP/GETTAB; see uuolib). PDP-10-specific; FORTRAN10 only, never strict F66/F77.
    dec_operators: bool = False  # operators beyond ANSI X3.9-1966 §6.1: the symbolic
    # relationals (== # < > <= >=, vs .EQ./.NE./.LT./.LE./.GT./.GE.), .XOR., and `^` as a
    # power operator (`**` is ANSI). .EQV./.NEQV. are F77-standard -- see eqv_operators.
    eqv_operators: bool = False  # the .EQV./.NEQV. logical-equivalence operators (F77 §6.6;
    # .XOR. and the symbolic relationals stay DEC-only under dec_operators)
    stmt_separator: bool = False  # `;` multi-statement lines (F66 is one statement per line)
    array_lower_bounds: bool = False  # DIMENSION A(lo:hi) explicit lower bounds (F66 is 1..n)
    slash_dim_bound: bool = False  # DEC's A(lo/hi) bound form (V5 6.2); off for F77, where the
    # only bound separator is ':' and '/' inside a bound is ordinary division (e.g. A(6/3:9))
    parameter_stmt: bool = False  # the PARAMETER statement (added in F77; not in ANSI F66)
    star_sizes: bool = False  # INTEGER*4 / REAL*8 byte-size type specifiers (DEC/F77)
    alt_return: bool = False  # alternate-return actual args in CALL ($n/&n/*n) (F77/DEC)
    block_if: bool = False  # block IF...THEN / ELSE IF / ELSE / END IF (F77; also FORTRAN-10 V5)
    do_while: bool = False  # DO WHILE (cond) / END DO (DEC/F90 ext; NOT in ANSI X3.9-1978)
    zero_trip_do: bool = False  # F77 §11.10 zero-trip DO (body skipped when the count is <=0);
    # F66 / DEC FORTRAN-10 run the body at least once (one-trip) -- a deliberate F66 divergence
    save_stmt: bool = False  # the SAVE statement (F77; a no-op here -- locals are already static)
    intrinsic_stmt: bool = False  # the INTRINSIC statement (F77; declares names as intrinsic)
    character_type: bool = False  # the F77 CHARACTER data type (decls, // concat, substrings,
    # LEN/CHAR/...). A string literal then evaluates to a str, not a Hollerith packed word.
    blank_null: bool = False  # blanks in a width'd numeric input field are IGNORED (BLANK=NULL),
    # the FORTRAN-10 V5 / F77 default. ANSI X3.9-1966 (7.2.3.6) instead reads them as zeros, so
    # F66 keeps blank_null=False; BN/BZ descriptors and OPEN BLANK= override at run time.

    # ---- strictness knobs (the only ones that REJECT rather than ACCEPT more) ----------------
    # These enforce an ANSI program constraint as a hard error. They are OFF for the lenient
    # real-compiler dialects (F66, FORTRAN-10 -- which accept the nonconforming form silently),
    # and ON only where the dialect is meant to model the standard strictly (F77).
    strict_stmt_order: bool = False  # F77 §3.5: a specification statement must precede all DATA,
    # statement-function, and executable statements -- a spec after an executable is rejected.

    # recursion: §15.5.2 prohibits a subprogram referencing itself. OFF on every standard dialect
    # (a re-entry is rejected -- forterp's static locals cannot represent it, and the period
    # compilers did not support it either). A procedure declared with the F90 RECURSIVE keyword may
    # recurse regardless of this flag (the per-procedure opt-in, like gfortran); turning this ON is
    # the global override (every procedure may recurse, like gfortran -frecursive). Either way the
    # nested activation gets correct per-call local storage. A capability gate, any dialect.
    recursion: bool = False

    # unlimited_rank: §5.1 caps an array at seven dimensions. Enforced by default (an 8-D+
    # declarator is rejected); turn ON to lift the cap. A relax gate, usable with any dialect.
    # (F66's stricter 3-dimension limit is left lenient -- an accept-more for the base dialect.)
    unlimited_rank: bool = False

    # carriage_control: the default device model for standard output (unit 6). True = line printer
    # (the first character of a formatted record is ASA carriage control, consumed -- the classic
    # FORTRAN-10 behavior); False = terminal/file (the first character is ordinary data, like
    # gfortran). §12.9.5.2.3 makes "which devices print" a processor choice, so each dialect picks:
    # F66/FORTRAN-10 = line printer (faithful to the era/DEC), F77 = terminal (modern, gfortran-
    # aligned). Overridable: an explicit carriage_control= to the engine wins over this default.
    carriage_control: bool = True

    # bounds_check: when ON, an array subscript outside its declared bounds (§5.4) is a hard error
    # (the gfortran -fcheck=bounds analog). OFF by default, preserving the faithful unchecked model
    # where deliberate over-/under-indexing traverses the COMMON/EQUIVALENCE storage sequence. A
    # diagnostic gate, usable with any dialect.
    bounds_check: bool = False


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
    list_directed_io=True,
    bare_format_width=True,
    f77_intrinsics=True,
    dec_library=True,
    uuo_library=True,
    dec_operators=True,
    eqv_operators=True,
    stmt_separator=True,
    array_lower_bounds=True,
    slash_dim_bound=True,  # DEC A(lo/hi) bound form
    parameter_stmt=True,
    star_sizes=True,
    alt_return=True,
    block_if=True,  # block IF is a FORTRAN-10 V5 construct
    do_while=True,  # DEC FORTRAN-10 has DO WHILE
    save_stmt=True,
    intrinsic_stmt=True,
    blank_null=True,  # FORTRAN-10 V5: width'd numeric input ignores blanks (BLANK=NULL default)
)
# ANSI X3.9-1978 (FORTRAN 77): the standard between F66 and the DEC superset. The full language --
# the CHARACTER type, list-directed I/O, the block IF, .EQV./.NEQV., zero-trip DO, and strict F77
# statement ordering are all on. DEC-only extensions (octal `"`, tab format, free-form input, TYPE/
# ACCEPT, ENCODE/DECODE, symbolic == operators, `;`, DO WHILE) stay off -- use FORTRAN10 for those.
F77 = Dialect(
    apostrophe_string=True,  # CHARACTER/Hollerith apostrophe constants
    implicit_stmt=True,
    expr_subscripts=True,
    array_lower_bounds=True,
    parameter_stmt=True,
    alt_return=True,
    mixed_complex_assign=True,
    f77_intrinsics=True,  # the F77 generic intrinsic library (DEC library + UUOs stay off)
    block_if=True,
    save_stmt=True,
    intrinsic_stmt=True,
    character_type=True,
    list_directed_io=True,  # F77 §12 standardized list-directed I/O
    eqv_operators=True,  # F77 §6.6 has .EQV./.NEQV.
    zero_trip_do=True,  # F77 §11.10 zero-trip DO loops
    blank_null=True,  # F77 §13.5.7: a width'd numeric field's blanks default to NULL (ignored)
    strict_stmt_order=True,  # F77 §3.5: specs must precede executables (hard error; FCVS-clean)
    carriage_control=False,  # standard output is a terminal (first char is data), like gfortran
)

# CLI / front-end name -> dialect, so every caller resolves the same names in one place.
DIALECTS = {"f66": F66, "fortran10": FORTRAN10, "f77": F77}
