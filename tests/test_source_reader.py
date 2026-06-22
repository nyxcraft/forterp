"""Fixed-form source reader (source.py) vs V5 manual Chapter 2 "Characters
and Lines".  These exercise the column-oriented line handling -- comment markers,
continuation field, multi-statement lines, debug lines -- not expression semantics.
"""

from conftest import out, run

H = "        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n        COMMON /OUT/ V(40)\n"
END = "        END\n"


# ---- comment lines: V5 2.3.3 markers are C/c, $, /, *, ! in column 1 ----
def test_all_column1_comment_markers_are_skipped():
    # one comment line per legal marker; none must affect the program
    body = (
        "C a classic comment\n"
        "c lower-case c too\n"
        "* asterisk comment\n"
        "! bang comment\n"
        "$ dollar comment\n"
        "/ slash comment\n"
        "        V(1)=7\n"
    )
    assert out(run(H + body + END), 1) == 7


def test_dollar_and_slash_comments_do_not_become_statements():
    # a line that WOULD be a syntax error if not treated as a comment
    body = "$ this = is ( not ) valid fortran\n/ neither // is ) this (\n        V(1)=3\n"
    assert out(run(H + body + END), 1) == 3


# ---- inline remark: '!' in the statement field (V5 2.3.3) ----
def test_inline_bang_remark_is_stripped():
    assert out(run(H + "        V(1)=5  ! set it to five\n" + END), 1) == 5


def test_bang_inside_a_string_is_not_a_remark():
    # the '!' lives inside a Hollerith/literal and must survive
    eng = run(H + "        V(1)=0\n        IF('A!B'=='A!B') V(1)=1\n" + END)
    assert out(eng, 1) == 1


# ---- continuation field: V5 2.2.2 any non-blank/non-zero char in column 6 ----
def test_ampersand_continuation():
    # '&' (a common continuation marker) in column 6
    eng = run(H + "        V(1)=1\n     &       +20\n" + END)
    assert out(eng, 1) == 21


def test_digit_continuation():
    # the INTRO-8 rule: a digit 1-9 in column 6 is a continuation line
    eng = run(H + "        V(1)=1\n     2       +40\n" + END)
    assert out(eng, 1) == 41


def test_zero_in_column6_is_not_a_continuation():
    # '0' in column 6 is an initial line, not a continuation
    eng = run(H + "        V(1)=1\n0       V(2)=9\n" + END)
    assert out(eng, 1) == 1
    assert out(eng, 2) == 9


# ---- multi-statement lines: V5 2.3.2 ';' separator, only first may be labelled ----
def test_semicolon_multistatement_line():
    eng = run(H + "        V(1)=2 ; V(2)=3 ; V(3)=V(1)+V(2)\n" + END)
    assert [out(eng, i) for i in range(1, 4)] == [2, 3, 5]


def test_semicolon_inside_string_is_not_a_separator():
    eng = run(H + "        V(1)=0\n        IF('A;B'=='A;B') V(1)=1\n" + END)
    assert out(eng, 1) == 1


# ---- debug lines: V5 2.3.4 'D'/'d' in column 1 = comment unless /DEBUG ----
def test_debug_line_skipped_by_default():
    eng = run(H + "        V(1)=1\nD       V(1)=99\n" + END)
    assert out(eng, 1) == 1  # the debug line did not execute


# ---- statement labels: V5 2.2.1 leading zeros/blanks ignored (00105 == 105) ----
def test_label_leading_zeros_ignored():
    src = H + "        GOTO 105\n        V(1)=99\n00105   V(1)=7\n" + END
    assert out(run(src), 1) == 7


# ---- cols 73+ field (V5 2.2.4): faithfully dropped by default (both dialects); the
#      SourceOptions recovery heuristic keeps spillover only when col-72 truncation would
#      cut a statement in half. This is source recovery, NOT a dialect feature.
import os  # noqa: E402
import tempfile  # noqa: E402

from forterp.source import SourceOptions, _trim_seqfield, scan_file  # noqa: E402


def _line(stmt_at7, tail_at73):
    # build a physical line: cols 1-6 blank, statement from col 7, tail from col 73
    head = "      " + stmt_at7
    return head.ljust(72) + tail_at73


def _spill_line():
    # a CALL whose closing ')' lands in column 73 (one past the 72-col field),
    # so cols 7-72 hold an unclosed '(' -- the reindented-spillover shape.
    body = "CALL STROUT('" + "Z" * 49 + "',10)"  # 67 chars -> ')' at col 7+66 = 73
    s = "      " + body
    assert len(s) == 73 and s[72] == ")"
    return s


def test_seqfield_dropped_after_complete_statement():
    # balanced statement by col 72 + a digit OR alphabetic sequence field -> drop it
    assert _trim_seqfield(_line("X=1", "00690001")) == _line("X=1", "00690001")[:72]
    assert _trim_seqfield(_line("X=1", "MAIN0010")) == _line("X=1", "MAIN0010")[:72]


def test_spillover_kept_when_it_completes_a_cut_statement():
    # closing paren spilled past col 72 (reindented spillover) -> keep whole
    s = _spill_line()
    assert _trim_seqfield(s) == s  # kept: tail ')' closes the open paren


def test_continued_statement_seqfield_still_dropped():
    # cols 7-72 end with an unclosed '(' because the stmt CONTINUES next line; the
    # cols 73+ digit field does NOT complete it -> drop the field, keep cols 7-72.
    s = "      IVCOMP = (IVON01 + IVON02) - (IVON03 * IVON04) / (IVON05 **".ljust(72) + "02000045"
    assert _trim_seqfield(s) == s[:72]


def test_seqfield_dropped_by_default_recovery_keeps_spillover():
    s = _spill_line()
    with tempfile.NamedTemporaryFile("w", suffix=".FOR", delete=False) as f:
        f.write(s + "\n        END\n")
        path = f.name
    try:
        # Default (both dialects): faithful hard 72-col cut. SourceOptions recovery (a
        # source-handling option, NOT a dialect) keeps the balanced spillover.
        strict = scan_file(path).statements[0].text
        lenient = (
            scan_file(path, options=SourceOptions(recover_shifted_cols=True)).statements[0].text
        )
    finally:
        os.unlink(path)
    assert strict.endswith("10")  # ')' in col 73 dropped -> unbalanced
    assert lenient.endswith("10)")  # lenient keeps the spilled ')'


# ---- DEC tab-format source lines (V5 2.2.2) + bare main program ------------
def test_tab_formatted_source_lines():
    # <TAB>stmt = initial line; <TAB><digit> = continuation (the common DEC
    # tab-format convention). Built with real tabs so the reader must honor the tab field.
    src = (
        "\tPROGRAM T\n\tIMPLICIT INTEGER(A-Z)\n\tCOMMON /OUT/ V(40)\n"
        "\tV(1)=2\n\t1\t+3\n\tEND\n"
    )  # the '\t1\t+3' line continues V(1)=2
    eng = run(src)
    assert out(eng, 1) == 5


def test_tab_label_field():
    # label before the tab:  100<TAB>CONTINUE
    src = (
        "\tPROGRAM T\n\tIMPLICIT INTEGER(A-Z)\n\tCOMMON /OUT/ V(40)\n"
        "\tGOTO 100\n\tV(1)=9\n100\tV(1)=7\n\tEND\n"
    )
    assert out(run(src), 1) == 7


def test_bare_main_program_without_program_statement():
    # the PROGRAM statement is optional (F66/FORTRAN-10); a file may start with the
    # main program body. The implicit main is named $MAIN.
    src = (
        "        IMPLICIT INTEGER(A-Z)\n        COMMON /OUT/ V(40)\n        V(1)=42\n        END\n"
    )
    eng = run(src, program="$MAIN")
    assert out(eng, 1) == 42


def test_dialect_gates_dec_lexer_extensions():
    # The front-end dialect is selectable: DEC FORTRAN-10 accepts the octal "nnn literal;
    # strict ANSI F66 rejects it -- proof the dialect param is wired, not cosmetic.
    import pytest

    from forterp.dialect import F66, FORTRAN10
    from forterp.lexer import LexError, tokenize

    assert tokenize('"101', FORTRAN10)[0].kind == "OCTAL"  # DEC octal literal -> 65
    with pytest.raises(LexError):
        tokenize('"101', F66)  # not an ANSI F66 literal
