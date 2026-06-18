"""FORTRAN-10 V5 compiler diagnostics (Appendix F) -- the lexical/syntactic subset
this front-end can detect, rendered in the faithful '?FTNXXX LINE:n text' format.
These fire only on INVALID source; valid programs (the game) emit none.
"""

from conftest import run
from f66.diagnostics import diag

PROG = ("        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n"
        "        COMMON /OUT/ V(40)\n")
END = "        END\n"


def errmsg(src):
    """Return the harness's parse-error text (empty string if it parsed clean)."""
    try:
        run(src)
    except AssertionError as e:
        return str(e)
    return ""


# ---- the renderer ----------------------------------------------------------
def test_diag_format_fatal_and_warning():
    assert diag("NRC", "STATEMENT NOT RECOGNIZED", 42) == \
        "?FTNNRC LINE:42 STATEMENT NOT RECOGNIZED"
    assert diag("CQL", line=7) == "?FTNCQL LINE:7 NO CLOSING QUOTE IN LITERAL"
    assert diag("LID", "IDENTIFIER 'X' MORE THAN SIX CHARACTERS", 3).startswith("%FTNLID")
    assert diag("NNF") == "?FTNNNF NO STATEMENT NUMBER ON FORMAT"   # no LINE when absent


# ---- lexical diagnostics ---------------------------------------------------
def test_unterminated_string_is_cql():
    m = errmsg(PROG + "        V(1)='OOPS\n" + END)
    assert "?FTNCQL" in m and "NO CLOSING QUOTE IN LITERAL" in m and "LINE:" in m


def test_illegal_character_is_iac():
    m = errmsg(PROG + "        V(1)=?\n" + END)
    assert "?FTNIAC" in m and "ILLEGAL ASCII CHARACTER" in m


# ---- syntactic diagnostics -------------------------------------------------
def test_missing_paren_is_fwe():
    m = errmsg(PROG + "        DIMENSION A(5\n" + END)
    assert "?FTNFWE" in m and "WHEN EXPECTING" in m


def test_unlabeled_format_is_nnf():
    m = errmsg(PROG + "        FORMAT(I5)\n" + END)
    assert "?FTNNNF" in m and "NO STATEMENT NUMBER ON FORMAT" in m


def test_diagnostics_carry_line_numbers():
    m = errmsg(PROG + "        FORMAT(I5)\n" + END)
    assert "LINE:4" in m            # the FORMAT is the 4th source line


# ---- %FTNLID warning channel (V5 3.3: >6-char names truncated, non-fatal) --
def test_ftnlid_warning_on_long_name_truncation():
    import tempfile, os
    from f66.source import scan_file, expand_includes
    from f66.parser import parse_units
    src = "        PROGRAM T\n        LONGNAME12 = 5\n        END\n"
    with tempfile.NamedTemporaryFile("w", suffix=".FOR", delete=False) as f:
        f.write(src); path = f.name
    try:
        stmts = expand_includes(scan_file(path).statements, os.path.dirname(path))
        errs, warns = [], []
        parse_units(stmts, on_error=lambda st, m: errs.append(m),
                    on_warn=lambda st, m: warns.append(m))
    finally:
        os.unlink(path)
    assert errs == []                                    # truncation is non-fatal
    assert any(w.startswith("%FTNLID") for w in warns)   # warning was emitted
    assert any("LONGNA" in w for w in warns)             # truncated to 6 chars


def test_no_warning_for_six_char_or_shorter_names():
    import tempfile, os
    from f66.source import scan_file, expand_includes
    from f66.parser import parse_units
    src = "        PROGRAM T\n        SIXCHR = 5\n        END\n"
    with tempfile.NamedTemporaryFile("w", suffix=".FOR", delete=False) as f:
        f.write(src); path = f.name
    try:
        stmts = expand_includes(scan_file(path).statements, os.path.dirname(path))
        warns = []
        parse_units(stmts, on_warn=lambda st, m: warns.append(m))
    finally:
        os.unlink(path)
    assert warns == []
