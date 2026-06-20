"""Fixed-form FORTRAN-66 / DEC FORTRAN-10 source reader.

Turns the raw column-oriented .FOR text into a stream of logical statements,
handling the fixed-form rules and the DEC extensions gated by the Dialect:

  * column 1 in 'C c * ! $ /'    -> full-line comment (F66 / V5 2.3.3)
  * column 1 in 'D d'            -> debug line (compiled only under /DEBUG;
                                    skipped by default, kept if debug=True)
  * column 6 non-blank/non-'0'   -> continuation of the previous statement
                                    (always '&' here, but any char is allowed)
  * columns 1-5                  -> statement label
  * columns 7+                   -> statement text
  * trailing  ! ...              -> inline comment (quote-aware)
  * ' ; ' separators             -> multiple statements on one line (quote-aware)
  * a lone '.' line              -> end-of-file artifact from the 1979 download
  * INCLUDE 'FILE/SWITCH'        -> reported (and optionally expanded)

Columns 73-80 are the identification/sequence field, which BOTH FORTRAN-10 (V5 2.2.4)
and F66 (3.3) treat as an automatic remark and drop unconditionally -- so the statement
is cols 7-72, full stop. That faithful behavior is the default.

`SourceOptions(recover_shifted_cols=True)` turns on a SOURCE-RECOVERY heuristic that is
NOT a language feature: drop cols 73+ as usual UNLESS truncating at column 72 would
obviously cut a statement in half (cols 7-72 left with an unclosed '(' or an unterminated
string) AND including cols 73+ makes it whole. This recovers source whose statement text
was nudged past col 72 -- e.g. period decks mechanically re-indented from their col-7
original, so a long statement spills its closing ')' into cols 73-74. It is orthogonal to
the `Dialect` (it copes with imperfect *input*, not with a dialect of the *language*), so
it lives here, off the dialect axis. Best-effort: it relaxes the obvious mid-statement
cases, not every one.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from forterp.dialect import F66


COMMENT_COL1 = set("Cc*!$/")  # V5 manual 2.3.3 comment-line markers
DEBUG_COL1 = set("Dd")


@dataclass(frozen=True)
class SourceOptions:
    """Source-recovery knobs -- ORTHOGONAL to the language `Dialect`. These cope with
    imperfect *input* (mechanically re-indented decks, download artifacts), not with
    FORTRAN language features, so they are kept off the dialect axis. Default = faithful,
    no recovery (statement is cols 7-72, the sequence field is dropped)."""

    recover_shifted_cols: bool = False  # keep statement text nudged into cols 73-80
    # (period source re-indented past its col-7 origin); see _trim_seqfield.


DEFAULT_OPTIONS = SourceOptions()


@dataclass
class Statement:
    label: int | None  # statement label, or None
    text: str  # statement source text (comments/labels stripped)
    file: str  # originating file
    line: int  # physical line number of the statement's first line
    kind: str = "stmt"  # 'stmt' or 'include'
    include_name: str = ""  # for kind == 'include'


@dataclass
class FileScan:
    path: str
    statements: list[Statement] = field(default_factory=list)
    n_physical: int = 0
    n_comment: int = 0
    n_debug: int = 0
    n_continuation: int = 0
    n_blank: int = 0


def _split_inline_comment(text: str, in_str: bool = False) -> tuple[str, bool]:
    """Drop a trailing '!' comment, ignoring '!' inside '...' strings. `in_str` is
    the open-string state inherited from the previous physical line (a character
    constant may span a continuation, carrying its quoting across the line break);
    the returned flag is the state at end of line, to thread into the next one."""
    out = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "'":
            if in_str and i + 1 < n and text[i + 1] == "'":
                out.append("''")
                i += 2
                continue
            in_str = not in_str
            out.append(c)
            i += 1
            continue
        if c == "!" and not in_str:
            break
        out.append(c)
        i += 1
    return "".join(out), in_str


def _split_semicolons(text: str) -> list[str]:
    """Split a logical line on top-level ';', ignoring ';' inside strings."""
    parts, buf = [], []
    i, n = 0, len(text)
    in_str = False
    while i < n:
        c = text[i]
        if c == "'":
            if in_str and i + 1 < n and text[i + 1] == "'":
                buf.append("''")
                i += 2
                continue
            in_str = not in_str
            buf.append(c)
            i += 1
            continue
        if c == ";" and not in_str:
            parts.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(c)
        i += 1
    parts.append("".join(buf))
    return parts


def _is_continuation(raw: str) -> bool:
    if len(raw) <= 5:
        return False
    col6 = raw[5]
    return raw[0:5].strip() == "" and col6 not in (" ", "0", "\t")


def _tab_split(raw: str):
    """DEC tab-format source line (FORTRAN-10 2.3): a TAB within the label field
    (cols 1-6) terminates it. Returns (label, is_continuation, body) or None if the
    line is not tab-formatted. After the TAB a digit 1-9 marks a continuation line;
    anything else is an initial line. (Space-formatted source never triggers this;
    much PDP-10 source -- and many editors -- emit tab-formatted lines.)"""
    tab = raw[:6].find("\t")
    if tab < 0:
        return None
    label, after = raw[:tab], raw[tab + 1 :]
    if after[:1] in "123456789":
        return label, True, after[1:]  # <TAB><digit> -> continuation
    return label, False, after  # <TAB> (or label<TAB>) -> initial line


def _statement_cut_midway(text: str) -> bool:
    """True if `text` (the cols 7-72 statement slice) is left dangling -- an unclosed
    '(' or an unterminated string literal -- ignoring a trailing '!' inline comment.
    Quote-aware: '' inside a string is an escaped apostrophe, not a close."""
    depth = 0
    in_str = False
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "'":
            if in_str and i + 1 < n and text[i + 1] == "'":
                i += 2
                continue
            in_str = not in_str
        elif not in_str:
            if c == "!":  # inline comment: the rest is not statement text
                break
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
        i += 1
    return in_str or depth > 0


def _trim_seqfield(raw: str) -> str:
    """Lenient cols-73+ handling. Columns 73-80 are normally an ignored sequence/ID
    field, so we drop them -- UNLESS truncating at column 72 would obviously cut a
    statement in half (cols 7-72 left with an unclosed paren or open string). In that
    case the spillover is real statement text, so keep the whole line. A genuine
    sequence field follows a complete, balanced statement and is dropped as usual.
    See the module docstring (lenient cols-73+ handling)."""
    if len(raw) <= 72 or not raw[72:].strip():
        return raw  # nothing meaningful past col 72
    # Keep the tail only if it COMPLETES the statement: cols 7-72 are cut mid-way
    # AND including cols 73+ makes them whole. A continued statement (closing paren
    # on the next physical line) or a real sequence field stays incomplete with the
    # tail appended, so it is still truncated -- only genuine spillover is kept.
    if _statement_cut_midway(raw[6:72]) and not _statement_cut_midway(raw[6:]):
        return raw
    return raw[:72]


def scan_file(path: str, debug: bool = False, dialect=F66, options=DEFAULT_OPTIONS) -> FileScan:
    """Scan a fixed-form source FILE into logical statements."""
    with open(path, "r", errors="replace") as fh:
        return scan_text(fh.read(), path, debug, dialect, options)


def scan_text(
    text: str,
    path: str = "<string>",
    debug: bool = False,
    dialect=F66,
    options=DEFAULT_OPTIONS,
) -> FileScan:
    """Scan fixed-form source TEXT into logical statements (no filesystem access).
    `path` only labels the produced statements for diagnostics."""
    fs = FileScan(path=path)
    strict = not options.recover_shifted_cols  # faithful 72-col cut unless recovering
    # ANSI F66 has no inline comments; only the DEC dialect strips a trailing '!'.
    if dialect.inline_comment:
        strip_comment = _split_inline_comment
    else:

        def strip_comment(body, instr):  # no-op: keep the body as-is
            return body, instr

    rawlines = text.splitlines()

    # The statement under construction: physical lines (an initial line plus its
    # continuations) accumulate here until flush() emits one or more logical statements
    # from them (one per top-level ';'). Tracks the label, the text fragments, the first
    # physical line number, and the open-string state carried across continuations.
    pending_label: int | None = None
    pending_frags: list[str] = []
    pending_line = 0
    pending_instr = False  # open-string state carried across continuation lines

    def flush():
        nonlocal pending_label, pending_frags, pending_line, pending_instr
        pending_instr = False
        if not pending_frags and pending_label is None:
            return
        joined = "".join(pending_frags)  # inline '!' comments already stripped per line
        # `;` multi-statement lines are a DEC extension; under F66 don't split -- the ';'
        # then reaches the lexer as an illegal character (F66 is one statement per line).
        parts = _split_semicolons(joined) if dialect.stmt_separator else [joined]
        for k, part in enumerate(parts):
            part = part.strip()
            if part == "":
                continue
            lab = pending_label if k == 0 else None
            up = part.upper()
            if up.startswith("INCLUDE"):
                name = _include_name(part)
                fs.statements.append(
                    Statement(lab, part, path, pending_line, kind="include", include_name=name)
                )
            else:
                fs.statements.append(Statement(lab, part, path, pending_line))
        pending_label = None
        pending_frags = []
        pending_line = 0

    for idx, raw in enumerate(rawlines, start=1):
        fs.n_physical += 1
        # F66 3.3 / FORTRAN-10 2.2.4: cols 73+ are an ignored identification field.
        raw = raw[:72] if strict else _trim_seqfield(raw)
        stripped = raw.strip()

        if stripped == "":
            fs.n_blank += 1
            continue
        if stripped == ".":  # 1979 download EOF artifact
            fs.n_blank += 1
            continue

        c1 = raw[0]
        if c1 in COMMENT_COL1:
            fs.n_comment += 1
            continue
        if c1 in DEBUG_COL1:
            fs.n_debug += 1
            if not debug:
                continue
            # treat as a normal statement when debugging is on
            raw = " " + raw[1:]

        ts = _tab_split(raw) if dialect.tab_format else None  # DEC tab-format (V5 2.2.2)
        if ts is not None:
            label_field, is_cont, body = ts
            # strip each physical line's trailing '!' comment BEFORE joining, so an
            # inline comment on a non-final continuation line can't swallow the lines
            # that follow it (FORTRAN-10 removes comments per line, then continues);
            # thread the open-string state so a '!' inside a continued literal stays.
            if is_cont:
                fs.n_continuation += 1
                body, pending_instr = strip_comment(body, pending_instr)
                pending_frags.append(body)
                continue
            flush()
            body, pending_instr = strip_comment(body, False)
            pending_label = int(label_field) if label_field.strip().isdigit() else None
            pending_frags = [body]
            pending_line = idx
            continue

        if _is_continuation(raw):
            fs.n_continuation += 1
            frag, pending_instr = strip_comment(raw[6:], pending_instr)
            pending_frags.append(frag)
            continue

        # initial line of a (possibly continued) statement
        flush()
        label_field = raw[0:5].strip()
        frag, pending_instr = strip_comment(raw[6:], False)
        pending_label = int(label_field) if label_field.isdigit() else None
        pending_frags = [frag]
        pending_line = idx

    flush()
    return fs


def _include_name(text: str) -> str:
    """Extract FILE from  INCLUDE 'FILE/SWITCH'  ."""
    q1 = text.find("'")
    q2 = text.find("'", q1 + 1)
    if q1 < 0 or q2 < 0:
        return ""
    inner = text[q1 + 1 : q2]
    return inner.split("/")[0]


def _resolve_include(include_dir: str, name: str) -> str | None:
    """Resolve an INCLUDE target with FORTRAN-10 semantics: an exact match first,
    then the default .FOR extension when none is given, then a case-insensitive
    file match (the TOPS-10 file system folded case and uppercased names, so
    `include 'param'` finds PARAM.FOR). Returns the path, or None if unresolved."""
    exact = os.path.join(include_dir, name)
    if os.path.isfile(exact):
        return exact
    base = os.path.basename(name)
    has_ext = "." in base
    if not has_ext and os.path.isfile(exact + ".FOR"):
        return exact + ".FOR"
    try:
        entries = os.listdir(include_dir or ".")
    except OSError:
        return None
    wanted = {base.lower()} | (set() if has_ext else {base.lower() + ".for"})
    for e in entries:
        if e.lower() in wanted:
            return os.path.join(include_dir, e)
    return None


def expand_includes(
    statements: list[Statement],
    include_dir: str,
    debug: bool = False,
    dialect=F66,
    _stack: frozenset = frozenset(),
) -> list[Statement]:
    """Expand INCLUDE statements in place.

    Cycle protection is a path *stack* (ancestors only), not a global seen-set,
    so the same file (e.g. COMMON.EMP) included by many subprograms is expanded
    into each of them -- which is what INCLUDE actually means.
    """
    out: list[Statement] = []
    for st in statements:
        if st.kind == "include":
            inc_path = _resolve_include(include_dir, st.include_name)
            if inc_path is None or inc_path in _stack:
                out.append(st)  # unresolved / cyclic: leave visible
                continue
            inc = scan_file(inc_path, debug=debug, dialect=dialect).statements
            out.extend(expand_includes(inc, include_dir, debug, dialect, _stack | {inc_path}))
        else:
            out.append(st)
    return out


def load_statements(
    path: str, debug: bool = False, include_dir: str | None = None, dialect=F66
) -> list[Statement]:
    """Load statements from a file, expanding INCLUDE directives in place."""
    if include_dir is None:
        include_dir = os.path.dirname(os.path.abspath(path))
    stmts = scan_file(path, debug=debug, dialect=dialect).statements
    return expand_includes(stmts, include_dir, debug=debug, dialect=dialect)
