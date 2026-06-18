"""Recursive-descent parser for FORTRAN-66 / DEC FORTRAN-10.

Consumes the (label, text) statements from `source` + tokens from `lexer`,
groups them into ProgramUnits, fills each unit's declaration tables, and parses
executable statements into the AST in `ast_nodes`.
"""

from __future__ import annotations

import glob
import os

from f66.lexer import tokenize, Token, LexError
from f66.dialect import FORTRAN10
from f66.source import scan_file, expand_includes
from f66.diagnostics import diag, show
from f66 import ast_nodes as A


# normalize relational/logical operator tokens -> canonical Binary op codes
_REL_OP = {"==": "EQ", "#": "NE", "<": "LT", ">": "GT", "<=": "LE", ">=": "GE"}
_REL_DOT = {".EQ.": "EQ", ".NE.": "NE", ".LT.": "LT", ".LE.": "LE", ".GT.": "GT", ".GE.": "GE"}
# V5 Table 4-7 operator hierarchy: .OR. is level 8, .EQV./.NEQV./.XOR. are level 9
# (looser than .OR.).  They are therefore parsed at separate precedence levels.
_OR_DOT = {".OR.": "OR"}
_EQV_DOT = {".EQV.": "EQV", ".NEQV.": "NEQV", ".XOR.": "XOR"}

DECL_KW = {
    "INTEGER",
    "REAL",
    "LOGICAL",
    "DOUBLE",
    "COMPLEX",
    "DIMENSION",
    "COMMON",
    "PARAMETER",
    "DATA",
    "IMPLICIT",
    "EXTERNAL",
}
TYPE_KW = {"INTEGER", "REAL", "LOGICAL", "DOUBLE", "COMPLEX"}


def _apply_size(base, size):
    """Map a type keyword + *n size modifier to our internal type name.
    REAL*8 -> double precision; INTEGER*2/*4 -> integer; LOGICAL*1/*4 -> logical."""
    if base == "DOUBLE":
        return "DOUBLE PRECISION"
    if base == "REAL" and size == 8:
        return "DOUBLE PRECISION"
    return base


IO_SPEC_KEYS = {"END", "ERR", "FMT", "UNIT", "REC", "IOSTAT"}


class ParseError(Exception):
    def __init__(self, detail, mnemonic="NRC"):
        super().__init__(detail)
        self.mnemonic = mnemonic  # FORTRAN-10 App-F diagnostic mnemonic


def fix_tokens(toks: list[Token]) -> list[Token]:
    """Repair blanks-insignificant gluing the lexer can't see: GOTO<label>.

    `GOTO400` / `GO TO 400` (-> one ID 'GOTO400' once blanks are removed... but
    here blanks survive, so only the no-space `GOTO400` glues) splits back into
    the GOTO keyword and its integer label.  No real identifier is 'GOTO'+digits.
    """
    out = []
    for t in toks:
        if (
            t.kind == "ID"
            and len(t.value) > 4
            and t.value.startswith("GOTO")
            and t.value[4:].isdigit()
        ):
            out.append(Token("ID", "GOTO", t.col))
            out.append(Token("INT", int(t.value[4:]), t.col))
        else:
            out.append(t)
    return out


# --- F66 3.1.6 blanks-insignificance (retry path only) --------------------------
# Blanks are not significant except inside '...'/Hollerith. Our normal lexer keeps
# blanks AS token separators -- faithful to well-formatted source. The three FCVS audit
# routines FOR 3.1.6 (FM010/011/021) instead put blanks INSIDE tokens (DIM EN SION,
# 3 2 7 6 7, K 5 6 78  9). We support that ONLY as a RETRY: a statement that fails the
# normal parse is re-tried with blanks removed (literal-aware) and a leading statement
# keyword re-spaced off its glued operand. Well-formatted source never fails the normal
# parse, so it never takes this path.

_RESPACE_KW = (
    "DOUBLEPRECISION",
    "DIMENSION",
    "EQUIVALENCE",
    "EXTERNAL",
    "COMPLEX",
    "INTEGER",
    "LOGICAL",
    "COMMON",
    "DOUBLE",
    "REAL",
    "DATA",
)


def _strip_blanks(text: str) -> str:
    """Remove blanks/tabs, preserving them inside '...' strings and nH Hollerith
    (where, per F66 3.1.6, blanks ARE significant)."""
    out = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "'":  # string: copy verbatim
            out.append(c)
            i += 1
            while i < n:
                if text[i] == "'":
                    if i + 1 < n and text[i + 1] == "'":  # escaped ''
                        out.append("''")
                        i += 2
                        continue
                    out.append("'")
                    i += 1
                    break
                out.append(text[i])
                i += 1
            continue
        if c in " \t":
            i += 1
            continue
        if c.isdigit():  # number, or nH Hollerith
            j = i
            while j < n and text[j].isdigit():
                j += 1
            if j < n and text[j] in "Hh":  # nH<count chars verbatim>
                cnt = int(text[i:j])
                out.append(text[i : j + 1] + text[j + 1 : j + 1 + cnt])
                i = j + 1 + cnt
                continue
            out.append(text[i:j])
            i = j
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _top_index(s: str, ch: str) -> int:
    """Index of `ch` at paren-depth 0 outside strings, else -1."""
    depth = 0
    in_str = False
    i = 0
    while i < len(s):
        c = s[i]
        if c == "'":
            if in_str and i + 1 < len(s) and s[i + 1] == "'":
                i += 2
                continue
            in_str = not in_str
        elif not in_str:
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
            elif c == ch and depth == 0:
                return i
        i += 1
    return -1


def _respace_stmt(s: str) -> str:
    """Re-insert one blank after a leading statement keyword that blank-removal glued
    to its operand (DIMENSIONIADN11 -> 'DIMENSION IADN11'; DO-loop label/var). Returns
    s unchanged when no leading keyword applies (assignments self-classify: IF3=.. and
    DO3=.. are left glued, so they parse as assignments, not IF/DO statements)."""
    up = s.upper()
    for kw in _RESPACE_KW:
        if up.startswith(kw):
            rest = s[len(kw) :]
            # a declaration is keyword + name-list with NO top-level '='. (REALLY=5
            # keeps its '=', so it is NOT respaced -> stays an assignment.)
            if rest[:1].isalpha() and _top_index(rest, "=") < 0:
                return kw + " " + rest
            return s
    if up.startswith("DO") and s[2:3].isdigit():
        rest = s[2:]  # after 'DO'
        eq = _top_index(rest, "=")  # DO<label><var> = e1,e2[,e3]
        if eq >= 0 and _top_index(rest[eq + 1 :], ",") >= 0:
            return "DO " + rest  # a real DO loop (has the comma)
    return s  # else assignment to var DO...


def pack5(s: str) -> int:
    """Left-justify up to 5 chars as 7-bit bytes in a 36-bit word, blank pad.
    Returns the SIGNED 36-bit value so it compares equal to packword()-stored
    char data everywhere (DATA, literals, GETCHX, and ACCEPT input alike)."""
    s = (s + "     ")[:5]
    v = 0
    for i, c in enumerate(s):
        v |= (ord(c) & 0x7F) << (29 - 7 * i)
    return v - (1 << 36) if v & (1 << 35) else v


# ----------------------------------------------------------------- the parser
class P:
    """A cursor over one statement's tokens, with expression + statement rules."""

    def __init__(self, toks: list[Token]):
        self.toks = toks
        self.pos = 0
        self._no_div = False  # in a dimension bound, '/' is a delimiter, not divide
        self.namelists = ()  # known NAMELIST group names (for I/O dispatch)
        self.warn = None  # optional callable(full_name) -> %FTNLID warning

    def _name6(self, name):
        """Truncate a symbolic name to 6 chars (V5 3.3). If chars are dropped, fire a
        %FTNLID warning through self.warn (non-fatal; the truncated name is still used)."""
        if len(name) > 6 and self.warn is not None:
            self.warn(name)
        return name[:6]

    # -- low level
    def cur(self):
        return self.toks[self.pos] if self.pos < len(self.toks) else None

    def nxt(self):
        return self.toks[self.pos + 1] if self.pos + 1 < len(self.toks) else None

    def at_end(self):
        return self.pos >= len(self.toks)

    def advance(self):
        t = self.toks[self.pos]
        self.pos += 1
        return t

    def is_op(self, v):
        t = self.cur()
        return t is not None and t.kind == "OP" and t.value == v

    def is_id(self, name=None):
        t = self.cur()
        if t is None or t.kind != "ID":
            return False
        return name is None or t.value == name

    def accept_op(self, v):
        if self.is_op(v):
            self.advance()
            return True
        return False

    def expect_op(self, v):
        if not self.is_op(v):
            raise ParseError(f"FOUND {show(self.cur())} WHEN EXPECTING {v!r}", "FWE")
        self.advance()

    def expect_id(self):
        t = self.cur()
        if t is None or t.kind != "ID":
            raise ParseError(f"FOUND {show(t)} WHEN EXPECTING AN IDENTIFIER", "FWE")
        self.advance()
        return self._name6(t.value)  # V5 3.3: symbolic names are limited to 6 chars

    def expect_int(self):
        t = self.cur()
        if t is None or t.kind not in ("INT", "OCTAL"):
            raise ParseError(f"FOUND {show(t)} WHEN EXPECTING A STATEMENT LABEL", "FWE")
        self.advance()
        return t.value

    # -- expressions
    def parse_expr(self):
        return self.p_equiv()

    def p_equiv(self):  # level 9 (lowest): .EQV. / .NEQV. / .XOR.
        n = self.p_or()
        while self.cur() and self.cur().kind == "DOTOP" and self.cur().value in _EQV_DOT:
            op = _EQV_DOT[self.advance().value]
            n = A.Binary(op, n, self.p_or())
        return n

    def p_or(self):  # level 8: .OR.
        n = self.p_and()
        while self.cur() and self.cur().kind == "DOTOP" and self.cur().value in _OR_DOT:
            op = _OR_DOT[self.advance().value]
            n = A.Binary(op, n, self.p_and())
        return n

    def p_and(self):
        n = self.p_not()
        while self.cur() and self.cur().kind == "DOTOP" and self.cur().value == ".AND.":
            self.advance()
            n = A.Binary("AND", n, self.p_not())
        return n

    def p_not(self):
        if self.cur() and self.cur().kind == "DOTOP" and self.cur().value == ".NOT.":
            self.advance()
            return A.Unary("NOT", self.p_not())
        return self.p_rel()

    def p_rel(self):
        n = self.p_add()
        t = self.cur()
        if t is not None:
            if t.kind == "OP" and t.value in _REL_OP:
                op = _REL_OP[self.advance().value]
                return A.Binary(op, n, self.p_add())
            if t.kind == "DOTOP" and t.value in _REL_DOT:
                op = _REL_DOT[self.advance().value]
                return A.Binary(op, n, self.p_add())
        return n

    def p_add(self):
        n = self.p_mul()
        while self.cur() and self.cur().kind == "OP" and self.cur().value in ("+", "-"):
            op = self.advance().value
            n = A.Binary(op, n, self.p_mul())
        return n

    def p_mul(self):
        ops = ("*",) if self._no_div else ("*", "/")  # '/' is a bound delimiter in dims
        n = self.p_unary()
        while self.cur() and self.cur().kind == "OP" and self.cur().value in ops:
            op = self.advance().value
            n = A.Binary(op, n, self.p_unary())
        return n

    def p_unary(self):
        if self.cur() and self.cur().kind == "OP" and self.cur().value in ("+", "-"):
            op = self.advance().value
            return A.Unary(op, self.p_unary())
        return self.p_pow()

    def p_pow(self):
        base = self.p_primary()
        if self.is_op("^"):
            self.advance()
            return A.Binary("^", base, self.p_unary())
        return base

    def p_primary(self):
        t = self.cur()
        if t is None:
            raise ParseError("unexpected end of expression")
        if t.kind == "INT":
            self.advance()
            return A.IntLit(t.value)
        if t.kind == "REAL":
            self.advance()
            return A.RealLit(t.value)
        if t.kind == "OCTAL":
            self.advance()
            return A.OctalLit(t.value)
        if t.kind == "STR":
            self.advance()
            return A.StrLit(t.value)
        if t.kind == "LOGIC":
            self.advance()
            return A.LogicalLit(t.value)
        if t.kind == "ID":
            name = self._name6(self.advance().value)  # V5 3.3: 6-char name limit
            if self.is_op("("):
                return A.Ref(name, self.parse_args())
            return A.Var(name)
        if t.kind == "OP" and t.value == "(":
            self.advance()
            e = self.parse_expr()
            if self.accept_op(","):  # complex constant (re, im) -- V5 Ch4
                im = self.parse_expr()
                self.expect_op(")")
                return A.Complex(e, im)
            self.expect_op(")")
            return e
        raise ParseError(f"unexpected token in expression: {t}")

    def parse_args(self):
        self.expect_op("(")
        args = []
        if not self.is_op(")"):
            args.append(self.parse_expr())
            while self.accept_op(","):
                args.append(self.parse_expr())
        self.expect_op(")")
        return args

    # -- I/O lists with implied-DO
    def parse_iolist(self):
        items = [self.parse_io_item()]
        while self.accept_op(","):
            items.append(self.parse_io_item())
        return items

    def parse_io_item(self):
        if self.is_op("("):
            info = self._implied_info()
            if info is not None:
                return self._parse_implied(info)
        return self.parse_expr()

    def _implied_info(self):
        """If the '(' at self.pos opens an implied-DO, return (close, eq, ctrl_comma)."""
        toks, i = self.toks, self.pos
        depth = 0
        close = eq_idx = None
        commas = []
        j = i
        while j < len(toks):
            t = toks[j]
            if t.kind == "OP" and t.value == "(":
                depth += 1
            elif t.kind == "OP" and t.value == ")":
                depth -= 1
                if depth == 0:
                    close = j
                    break
            elif t.kind == "OP" and t.value == "=" and depth == 1 and eq_idx is None:
                eq_idx = j
            elif t.kind == "OP" and t.value == "," and depth == 1:
                commas.append(j)
            j += 1
        if close is None or eq_idx is None:
            return None
        ctrl_comma = None
        for c in commas:
            if c < eq_idx:
                ctrl_comma = c
        if ctrl_comma is None:
            return None
        return (close, eq_idx, ctrl_comma)

    def _parse_implied(self, info):
        close, eq_idx, cc = info
        body = self.toks[self.pos + 1 : cc]
        ctrl = self.toks[cc + 1 : close]
        items = P(body).parse_iolist()
        cp = P(ctrl)
        var = cp.expect_id()
        cp.expect_op("=")
        e1 = cp.parse_expr()
        cp.expect_op(",")
        e2 = cp.parse_expr()
        e3 = cp.parse_expr() if cp.accept_op(",") else None
        self.pos = close + 1
        return A.ImpliedDo(items, var, e1, e2, e3)

    # -- executable statements
    def parse_exec(self):
        t = self.cur()
        kw = t.value if (t and t.kind == "ID") else None
        nx = self.nxt()
        if kw == "IF" and nx and nx.kind == "OP" and nx.value == "(":
            return self.parse_if()
        if kw == "DO" and self._looks_like_do():
            return self.parse_do()
        if kw == "GOTO" or (kw == "GO" and nx and nx.kind == "ID" and nx.value == "TO"):
            return self.parse_goto()
        if kw == "ASSIGN" and nx and nx.kind == "INT":  # ASSIGN <label> TO <var>
            self.advance()
            label = self.expect_int()
            if self.is_id("TO"):
                self.advance()
            return A.AssignLabel(tgt=label, var=self.expect_id())
        if kw == "ENTRY":  # V5 15.7: alternate entry point
            self.advance()
            ename = self.expect_id()
            eparams = []
            if self.is_op("("):
                self.advance()
                if not self.is_op(")"):
                    while True:
                        if self.is_op("*"):  # alternate-return placeholder dummy
                            self.advance()
                            eparams.append("*")
                        else:
                            eparams.append(self.expect_id())
                        if not self.accept_op(","):
                            break
                self.expect_op(")")
            return A.EntryStmt(name=ename, params=eparams)
        if kw in ("ENCODE", "DECODE"):  # V5 10.15: internal formatted I/O
            return self.parse_encode_decode(kw)
        if kw == "CALL":
            return self.parse_call()
        if kw == "RETURN":
            self.advance()
            expr = self.parse_expr() if not self.at_end() else None
            return A.Return(expr=expr)
        if kw in ("STOP", "PAUSE"):
            self.advance()
            code = None
            if not self.at_end():
                t2 = self.cur()
                if t2.kind in ("INT", "OCTAL", "STR"):
                    code = self.advance().value
            return A.StopStmt(code=code) if kw == "STOP" else A.PauseStmt(code=code)
        if kw == "CONTINUE":
            self.advance()
            return A.Continue()
        if (
            kw in ("TYPE", "ACCEPT", "PRINT", "PUNCH")
            and nx
            and (
                nx.kind in ("INT", "OCTAL")
                or (nx.kind == "OP" and nx.value == "*")
                or (nx.kind == "ID" and nx.value[:6] in self.namelists)
            )
        ):
            return self.parse_type_io(kw)
        if kw in ("READ", "WRITE") and nx and nx.kind == "OP" and nx.value == "(":
            return self.parse_readwrite(kw)
        if kw == "FIND" and nx and nx.kind == "OP" and nx.value == "(":
            return self.parse_find()
        if (
            kw in ("READ", "WRITE", "REREAD")
            and nx
            and (  # default-device form
                nx.kind in ("INT", "OCTAL")
                or (nx.kind == "OP" and nx.value == "*")
                or (nx.kind == "ID" and nx.value[:6] in self.namelists)
            )
        ):
            return self.parse_default_io(kw)
        if kw == "DEFINE" and nx and nx.kind == "ID" and nx.value == "FILE":
            return self.parse_define_file()
        if kw in ("OPEN", "CLOSE") and nx and nx.kind == "OP" and nx.value == "(":
            return self.parse_filectl(kw)
        if kw in ("REWIND", "BACKSPACE", "ENDFILE"):  # bare unit or (specs)
            return self.parse_filectl(kw)
        if kw == "SKIP" and nx and nx.kind == "ID" and nx.value in ("RECORD", "FILE"):
            self.advance()  # SKIP
            verb = "SKIPREC" if self.advance().value == "RECORD" else "SKIPFILE"
            specs = {} if self.at_end() else {"UNIT": self.parse_expr()}
            return A.FileCtl(verb=verb, specs=specs)
        return self.parse_assign()

    def _looks_like_do(self):
        # DO <label> <var> = ...
        return (
            self.nxt()
            and self.nxt().kind in ("INT", "OCTAL")
            and self.pos + 2 < len(self.toks)
            and self.toks[self.pos + 2].kind == "ID"
            and self.pos + 3 < len(self.toks)
            and self.toks[self.pos + 3].kind == "OP"
            and self.toks[self.pos + 3].value == "="
        )

    def parse_if(self):
        self.advance()  # IF
        self.expect_op("(")
        cond = self.parse_expr()
        self.expect_op(")")
        t = self.cur()
        if t is not None and t.kind in ("INT", "OCTAL"):
            labels = [self.expect_int()]
            while self.accept_op(","):
                labels.append(self.expect_int())
            return A.IfBranch(cond=cond, labels=labels)
        return A.IfLogical(cond=cond, stmt=self.parse_exec())

    def parse_do(self):
        self.advance()  # DO
        term = self.expect_int()
        var = self.expect_id()
        self.expect_op("=")
        e1 = self.parse_expr()
        self.expect_op(",")
        e2 = self.parse_expr()
        e3 = self.parse_expr() if self.accept_op(",") else None
        return A.Do(var=var, start=e1, stop=e2, step=e3, term_label=term)

    def parse_goto(self):
        if self.is_id("GO"):
            self.advance()
            self.advance()  # GO TO
        else:
            self.advance()  # GOTO
        if self.is_op("("):
            self.advance()
            labels = [self.expect_int()]
            while self.accept_op(","):
                labels.append(self.expect_int())
            self.expect_op(")")
            self.accept_op(",")
            return A.CompGoto(labels=labels, index=self.parse_expr())
        t = self.cur()
        if t and t.kind == "ID":  # assigned GOTO: GO TO N [,(...)]
            var = self.expect_id()
            labels = []
            if self.accept_op(","):
                self.expect_op("(")
                labels.append(self.expect_int())
                while self.accept_op(","):
                    labels.append(self.expect_int())
                self.expect_op(")")
            return A.AssignedGoto(var=var, labels=labels)
        return A.Goto(target=self.expect_int())

    def parse_call(self):
        self.advance()  # CALL
        name = self.expect_id()
        args = []
        if self.is_op("("):
            self.advance()
            if not self.is_op(")"):
                args.append(self._call_arg())
                while self.accept_op(","):
                    args.append(self._call_arg())
            self.expect_op(")")
        return A.Call(name=name, args=args)

    def _call_arg(self):
        """A CALL actual: a normal expression, or a $nnn/*nnn alternate-return label."""
        t = self.cur()
        if t and t.kind == "OP" and t.value in ("$", "*", "&"):
            nx = self.nxt()
            if nx and nx.kind == "INT":
                self.advance()  # $ / * / &
                return A.LabelArg(label=self.advance().value)
        return self.parse_expr()

    def parse_equivalence(self, unit):
        """EQUIVALENCE (v1,v2,...),(w1,...),... -- storage sharing (V5 6.6). Each
        entity is name or name(subscripts); subscripts are integer constants, kept
        as expr nodes and const-evaluated at layout time."""
        self.advance()  # EQUIVALENCE
        while self.is_op("("):
            self.advance()
            group = []
            while True:
                name = self.expect_id()
                subs = []
                if self.is_op("("):  # array element with constant subscripts
                    self.advance()
                    while True:
                        subs.append(self.parse_expr())
                        if not self.accept_op(","):
                            break
                    self.expect_op(")")
                group.append((name, subs))
                if not self.accept_op(","):
                    break
            self.expect_op(")")
            unit.equivs.append(group)
            self.accept_op(",")  # optional comma between groups

    def parse_namelist(self, unit):
        """NAMELIST/N1/A1,A2,.../N2/.../ -- declare named I/O lists (V5 Ch11)."""
        self.advance()  # NAMELIST
        while self.is_op("/"):
            self.advance()  # opening slash
            gname = self.expect_id()
            self.expect_op("/")  # closing slash of the group name
            items = []
            while not self.at_end() and not self.is_op("/"):
                items.append(self.parse_io_item())
                if not self.accept_op(","):
                    break
            unit.namelists[gname] = items

    def _io_fmt(self):
        """Parse an I/O format reference: '*' (list-directed), an INT label, or an
        identifier (a NAMELIST group name -- returned as the bare name string)."""
        if self.accept_op("*"):
            return "*"
        if self.cur() and self.cur().kind in ("INT", "OCTAL"):
            return self.advance().value
        return self.expect_id()

    def parse_encode_decode(self, kw):
        """ENCODE(count, fmt, buf) iolist / DECODE(...) -- internal formatted I/O
        to a packed-ASCII buffer (V5 10.15)."""
        self.advance()  # ENCODE / DECODE
        self.expect_op("(")
        count = self.parse_expr()
        self.expect_op(",")
        if self.cur() and self.cur().kind in ("INT", "OCTAL"):
            fmt = self.advance().value  # FORMAT statement label
        elif self.accept_op("*"):
            fmt = "*"
        else:
            fmt = self.parse_expr()  # (runtime format held in a variable)
        self.expect_op(",")
        buf = self.parse_io_item()  # the character buffer (variable / array)
        self.expect_op(")")
        items = self.parse_iolist() if not self.at_end() else []
        return A.EncDec(decode=(kw == "DECODE"), count=count, fmt=fmt, buf=buf, items=items)

    def parse_type_io(self, kw):
        self.advance()  # TYPE / ACCEPT / PRINT
        fmt = self._io_fmt()  # '*' | label | NAMELIST name
        items = self.parse_iolist() if self.accept_op(",") else []
        if kw == "ACCEPT":  # input; TYPE/PRINT/PUNCH are output
            return A.AcceptStmt(fmt=fmt, items=items)
        return A.TypeStmt(fmt=fmt, items=items)

    def parse_default_io(self, kw):
        """READ/WRITE/REREAD without a (unit): default device (card reader / line
        printer) -- routed to the terminal in our model."""
        self.advance()  # READ / WRITE / REREAD
        fmt = self._io_fmt()  # '*' | label | NAMELIST name
        items = self.parse_iolist() if self.accept_op(",") else []
        if kw == "WRITE":
            return A.TypeStmt(fmt=fmt, items=items)
        return A.AcceptStmt(fmt=fmt, items=items, reread=(kw == "REREAD"))

    def parse_readwrite(self, kw):
        self.advance()  # READ / WRITE
        self.expect_op("(")
        unit = self.p_add()  # arithmetic only, so '#'/'\'' (rec sep) survive
        fmt = None
        specs = {}
        if self.is_op("#") or self.is_op("'"):  # V5 10.3.5: random record  u#r / u'r
            self.advance()
            specs["REC"] = self.p_add()
        while self.accept_op(","):
            if (
                self.is_id()
                and self.cur().value in IO_SPEC_KEYS
                and self.nxt()
                and self.nxt().kind == "OP"
                and self.nxt().value == "="
            ):
                key = self.advance().value
                self.advance()  # '='
                if self.cur() and self.cur().kind in ("INT", "OCTAL"):
                    specs[key] = self.advance().value
                else:
                    specs[key] = self.parse_expr()
            elif self.cur() and self.cur().kind in ("INT", "OCTAL"):
                fmt = self.advance().value
            elif self.accept_op("*"):
                fmt = "*"
            else:
                fmt = self.parse_expr()
        self.expect_op(")")
        items = self.parse_iolist() if not self.at_end() else []
        return A.IoStmt(mode=kw, unit=unit, fmt=fmt, specs=specs, items=items)

    def parse_define_file(self):
        """DEFINE FILE u(m,n,U,v) [,u2(...)...] (V5 10.3.5): declare random-access
        units -- m records of n words, access-mode letter U/E/L, associated variable v."""
        self.advance()  # DEFINE
        self.advance()  # FILE
        defs = []
        while True:
            unit = self.p_add()
            self.expect_op("(")
            maxrec = self.parse_expr()
            self.expect_op(",")
            recsize = self.parse_expr()
            self.expect_op(",")
            self.expect_id()  # access-mode letter (U/E/L) -- not modeled
            self.expect_op(",")
            assoc = self.expect_id()  # associated variable (next-record pointer)
            self.expect_op(")")
            defs.append({"unit": unit, "maxrec": maxrec, "recsize": recsize, "assoc": assoc})
            if not self.accept_op(","):
                break
        return A.DefineFile(defs=defs)

    def parse_find(self):
        """FIND(u#r) / FIND(u'r) -- position a random-access file (V5 10.14)."""
        self.advance()  # FIND
        self.expect_op("(")
        unit = self.p_add()
        specs = {}
        if self.is_op("#") or self.is_op("'"):
            self.advance()
            specs["REC"] = self.p_add()
        self.expect_op(")")
        return A.IoStmt(mode="FIND", unit=unit, fmt=None, specs=specs, items=[])

    def parse_filectl(self, kw):
        self.advance()  # OPEN / CLOSE / REWIND / BACKSPACE / ENDFILE
        specs = {}
        if self.is_op("("):
            self.advance()
            # positional unit "REWIND(1)" vs keyword specs "OPEN(UNIT=1,...)"
            if not (self.is_id() and self.nxt() and self.nxt().value == "="):
                specs["UNIT"] = self.parse_expr()
            while not self.is_op(")"):
                kt = self.cur()  # OPEN keyword: NOT a 6-char symbolic name
                if kt is None or kt.kind != "ID":
                    raise ParseError(f"FOUND {show(kt)} WHEN EXPECTING AN IDENTIFIER", "FWE")
                key = self.advance().value
                self.expect_op("=")
                t = self.cur()
                if t is not None and t.kind in ("INT", "OCTAL", "STR"):
                    specs[key] = self.advance().value
                else:
                    specs[key] = self.parse_expr()
                if not self.accept_op(","):
                    break
            self.expect_op(")")
        elif not self.at_end():  # bare unit form: REWIND 1
            specs["UNIT"] = self.parse_expr()
        return A.FileCtl(verb=kw, specs=specs)

    def parse_assign(self):
        name = self.expect_id()
        while self.is_id():  # blanks-insignificant: merge id run
            name += self.advance().value
        name = self._name6(name)  # V5 3.3: 6-char name limit (after merge)
        if self.is_op("("):
            target = A.Ref(name, self.parse_args())
        else:
            target = A.Var(name)
        self.expect_op("=")
        return A.Assign(target=target, expr=self.parse_expr())

    # -- declarations (each parses a full statement into `unit`)
    def parse_dims(self, consts):
        self.expect_op("(")
        dims = []
        saved, self._no_div = self._no_div, True  # V5 6.2: ':' OR '/' delimits bounds
        try:
            while True:
                lo_n = self.parse_expr()
                if self.accept_op(":") or self.accept_op("/"):
                    hi_n = self.parse_expr()
                    dims.append((_dim_bound(lo_n, consts), _dim_bound(hi_n, consts)))
                else:
                    dims.append((1, _dim_bound(lo_n, consts)))
                if not self.accept_op(","):
                    break
        finally:
            self._no_div = saved
        self.expect_op(")")
        return dims

    def opt_size(self):
        """Consume an optional *n size modifier (e.g. REAL*8); return n or None."""
        if self.is_op("*"):
            self.advance()
            t = self.advance()
            return t.value if t.kind in ("INT", "OCTAL") else None
        return None

    def parse_type_decl(self, unit, base, default_type):
        # caller already consumed the type keyword(s) and any keyword *n size.
        # `base` is the bare keyword (REAL/INTEGER/...) for per-variable *n overrides.
        while not self.at_end():
            name = self.expect_id()
            size = self.opt_size()  # per-variable size, e.g. B*8
            unit.types[name] = _apply_size(base, size) if size else default_type
            if self.is_op("("):
                unit.arrays[name] = self.parse_dims(unit.consts)
            if not self.accept_op(","):
                break

    def parse_dimension(self, unit):
        self.advance()  # DIMENSION
        while not self.at_end():
            name = self.expect_id()
            unit.arrays[name] = self.parse_dims(unit.consts)
            if not self.accept_op(","):
                break

    def parse_common(self, unit):
        self.advance()  # COMMON
        while not self.at_end():
            if self.is_op("/"):
                self.advance()
                block = self.expect_id() if self.is_id() else ""  # /name/ or // (blank)
                self.expect_op("/")
            else:
                block = ""  # COMMON list  ->  blank (unlabeled) common
            members = []
            while True:
                name = self.expect_id()
                dims = None
                if self.is_op("("):
                    dims = self.parse_dims(unit.consts)
                    unit.arrays[name] = dims
                members.append((name, dims))
                if self.is_op("/") or self.at_end():
                    break
                self.expect_op(",")
            unit.commons.append((block, members))

    def parse_parameter(self, unit):
        self.advance()  # PARAMETER
        paren = self.accept_op("(")
        while not self.at_end():
            name = self.expect_id()
            self.expect_op("=")
            unit.consts[name] = const_eval(self.parse_expr(), unit.consts)
            if not self.accept_op(","):
                break
        if paren:
            self.accept_op(")")

    def parse_implicit(self, unit):
        self.advance()  # IMPLICIT
        while not self.at_end():
            typ = self.advance().value  # INTEGER/REAL/...
            if typ == "DOUBLE" and self.is_id("PRECISION"):
                self.advance()
                typ = "DOUBLE PRECISION"
            self.expect_op("(")
            while True:
                a = self.expect_id()
                if self.accept_op("-"):
                    b = self.expect_id()
                    for o in range(ord(a), ord(b) + 1):
                        unit.implicit[chr(o)] = typ
                else:
                    unit.implicit[a] = typ
                if not self.accept_op(","):
                    break
            self.expect_op(")")
            if not self.accept_op(","):
                break

    def parse_data(self, unit):
        self.advance()  # DATA
        while not self.at_end():
            # target list, '/'-delimited -- must NOT run through parse_expr,
            # since '/' is also the division operator
            targets = []
            while True:
                if self.is_op("("):
                    targets.append(self.parse_io_item())  # implied-DO target
                else:
                    name = self.expect_id()
                    if self.is_op("("):
                        targets.append(A.Ref(name, self.parse_args()))
                    else:
                        targets.append(A.Var(name))
                if not self.accept_op(","):
                    break
            self.expect_op("/")
            values = []
            while not self.is_op("/"):
                count = 1
                v = self.parse_data_value()
                if self.is_op("*"):  # n*value repeat
                    self.advance()
                    count = v
                    v = self.parse_data_value()
                values.append((count, v))
                if not self.accept_op(","):
                    break
            self.expect_op("/")
            unit.data.append((targets, values))
            self.accept_op(",")

    def parse_data_value(self):
        neg = False
        if self.accept_op("-"):
            neg = True
        elif self.accept_op("+"):
            pass
        if self.is_op("("):  # complex constant (re, im) in DATA
            self.advance()
            re = self.parse_data_value()
            self.expect_op(",")
            im = self.parse_data_value()
            self.expect_op(")")
            return A.Complex(re, im)
        t = self.cur()
        if t is None:
            raise ParseError("expected DATA value")
        if t.kind in ("INT", "OCTAL"):
            self.advance()
            return -t.value if neg else t.value
        if t.kind == "REAL":
            self.advance()
            return -t.value if neg else t.value
        if t.kind == "STR":
            self.advance()
            return A.StrLit(t.value)
        if t.kind == "LOGIC":
            self.advance()
            return t.value
        if t.kind == "ID":
            return A.Var(self._name6(self.advance().value))  # PARAMETER ref (V5 3.3: 6-char)
        raise ParseError(f"bad DATA value: {t}")


def _dim_bound(node, consts):
    """A dimension bound: a constant int when possible, else the AST expression
    (an adjustable dimension whose dummy-arg value is resolved at run time)."""
    try:
        return const_eval(node, consts)
    except ParseError:
        return node


def const_eval(node, consts):
    if isinstance(node, A.IntLit):
        return node.value
    if isinstance(node, A.OctalLit):
        return node.value
    if isinstance(node, A.RealLit):
        return node.value
    if isinstance(node, A.StrLit):
        return node.value  # kept raw: the engine packs it via its Target (no
        # target at parse time). See Engine._const_value.
    if isinstance(node, A.Var):
        if node.name in consts:
            return consts[node.name]
        raise ParseError(f"unknown constant {node.name!r}")
    if isinstance(node, A.Unary):
        v = const_eval(node.operand, consts)
        return -v if node.op == "-" else v
    if isinstance(node, A.Binary):
        a = const_eval(node.left, consts)
        b = const_eval(node.right, consts)
        if node.op == "+":
            return a + b
        if node.op == "-":
            return a - b
        if node.op == "*":
            return a * b
        if node.op == "/":
            return int(a / b) if isinstance(a, float) or isinstance(b, float) else a // b
        if node.op == "^":
            return a**b
    raise ParseError(f"non-constant expression: {node}")


# ------------------------------------------------------- unit-level structure
def _is_header(toks):
    if not toks:
        return False
    v0 = toks[0].value if toks[0].kind == "ID" else None
    if v0 in ("SUBROUTINE", "PROGRAM", "FUNCTION"):
        return True
    if v0 == "BLOCKDATA" or (
        v0 == "BLOCK" and len(toks) > 1 and toks[1].kind == "ID" and toks[1].value == "DATA"
    ):
        return True  # BLOCK DATA [name]  (V5 Ch16)
    if v0 in TYPE_KW:
        for t in toks[1:4]:
            if t.kind == "ID" and t.value == "FUNCTION":
                return True
    return False


def _parse_header(toks):
    p = P(toks)
    ret_type = None
    v0 = toks[0].value if toks[0].kind == "ID" else None
    if v0 == "BLOCKDATA" or v0 == "BLOCK":  # BLOCK DATA [name] (V5 Ch16)
        p.advance()  # BLOCK / BLOCKDATA
        if v0 == "BLOCK":
            p.expect_id()  # DATA
        name = p.expect_id() if p.is_id() else "$BLOCKDATA"  # name is optional
        return A.ProgramUnit(kind="blockdata", name=name)
    if p.is_id() and p.cur().value in TYPE_KW and p.cur().value not in ("SUBROUTINE", "PROGRAM"):
        # could be a typed FUNCTION header
        typ = p.advance().value
        if typ == "DOUBLE" and p.is_id("PRECISION"):
            p.advance()
            typ = "DOUBLE PRECISION"
        ret_type = typ
        # now expect FUNCTION
        p.expect_id()  # 'FUNCTION'
        kind = "function"
    else:
        kw = p.advance().value
        kind = {"SUBROUTINE": "subroutine", "PROGRAM": "program", "FUNCTION": "function"}[kw]
    name = p.expect_id()
    params = []
    if p.is_op("("):
        p.advance()
        if not p.is_op(")"):
            while True:
                if p.is_op("*"):  # alternate-return placeholder dummy
                    p.advance()
                    params.append("*")
                else:
                    params.append(p.expect_id())
                if not p.accept_op(","):
                    break
        p.expect_op(")")
    return A.ProgramUnit(kind=kind, name=name, params=params, ret_type=ret_type)


def _format_body(text):
    """Return the raw '(...)' body of a FORMAT statement."""
    i = text.find("(")
    if i < 0:
        return ""
    return text[i:]


def parse_units(statements, *, on_error=None, on_warn=None, dialect=FORTRAN10):
    """Group expanded statements into ProgramUnits and parse each one. on_warn(st, msg)
    receives non-fatal diagnostics (e.g. %FTNLID, 6-char-name truncation). `dialect`
    selects the front-end extensions (default DEC FORTRAN-10)."""
    units = []
    unit = None
    for st in statements:
        if st.kind == "include":
            continue
        try:
            toks = fix_tokens(tokenize(st.text, dialect))
        except LexError as e:
            if on_error:
                on_error(st, diag(e.mnemonic, str(e), st.line))
            continue
        if not toks:
            continue

        kw = toks[0].value if toks[0].kind == "ID" else None

        if _is_header(toks):
            if unit is not None:
                units.append(unit)
            try:
                unit = _parse_header(toks)
            except ParseError as e:
                if on_error:
                    on_error(st, diag(e.mnemonic, str(e), st.line))
                unit = A.ProgramUnit(kind="subroutine", name="?")
            continue

        if unit is None:  # statements before any header begin the
            unit = A.ProgramUnit(kind="program", name="$MAIN")  # main program (the
            #            PROGRAM statement is optional in F66/FORTRAN-10; Adventure omits it)

        if kw == "END" and len(toks) == 1:
            units.append(unit)
            unit = None
            continue

        n_data, n_code = len(unit.data), len(unit.code)
        try:
            _route(unit, st, toks, on_warn)
        except (ParseError, LexError) as e:
            # F66 3.1.6 blanks-insignificance retry (well-formed source never reaches here).
            del unit.data[n_data:]  # undo any partial append before retry
            del unit.code[n_code:]
            norm = _respace_stmt(_strip_blanks(st.text))
            if norm != st.text:
                try:
                    _route(unit, st, fix_tokens(tokenize(norm, dialect)), on_warn)
                    continue
                except (ParseError, LexError):
                    del unit.data[n_data:]
                    del unit.code[n_code:]
            if on_error:
                on_error(st, diag(e.mnemonic, str(e), st.line))

    if unit is not None:
        units.append(unit)
    return units


def _route(unit, st, toks, on_warn=None):
    kw = toks[0].value if toks[0].kind == "ID" else None
    p = P(toks)
    p.namelists = unit.namelists  # so ACCEPT/TYPE/READ <namelist> dispatches right
    if on_warn is not None:  # %FTNLID: 6-char-name truncation (V5 3.3)
        p.warn = lambda nm: on_warn(
            st, diag("LID", f"NAME '{nm}' TRUNCATED TO '{nm[:6]}'", st.line)
        )

    if kw == "FORMAT":
        if st.label is None:
            raise ParseError("NO STATEMENT NUMBER ON FORMAT", "NNF")
        unit.formats[st.label] = _format_body(st.text)
        return
    if kw == "IMPLICIT":
        p.parse_implicit(unit)
        return
    if kw == "DIMENSION":
        p.parse_dimension(unit)
        return
    if kw == "COMMON":
        p.parse_common(unit)
        return
    if kw == "PARAMETER":
        p.parse_parameter(unit)
        return
    if kw == "DATA":
        p.parse_data(unit)
        return
    if kw == "EXTERNAL":
        p.advance()
        while not p.at_end():
            p.accept_op("*") or p.accept_op("&")  # V5 15.3: */& overrides an intrinsic name
            unit.externals.add(p.expect_id())
            if not p.accept_op(","):
                break
        return
    if kw == "NAMELIST":
        p.parse_namelist(unit)
        return
    if kw == "EQUIVALENCE":
        p.parse_equivalence(unit)
        return
    if kw in TYPE_KW and not _is_header(toks):
        base = p.advance().value
        if base == "DOUBLE" and p.is_id("PRECISION"):
            p.advance()
        size = p.opt_size()  # REAL*8 etc. on the type keyword
        p.parse_type_decl(unit, base, _apply_size(base, size))
        return

    # executable
    stmt = p.parse_exec()
    # FORTRAN-66 statement function: name(d1,d2,...)=expr appearing before any
    # executable statement, where `name` is NOT a declared array and the subscripts
    # are plain dummy names. (Distinct from an array-element assignment, whose name
    # is dimensioned; the array guard keeps the two cases unambiguous.)
    if (
        isinstance(stmt, A.Assign)
        and isinstance(stmt.target, A.Ref)
        and stmt.target.name not in unit.arrays
        and st.label is None
        and not unit.code
        and stmt.target.args
        and all(isinstance(a, A.Var) for a in stmt.target.args)
    ):
        unit.stmt_funcs[stmt.target.name] = ([a.name for a in stmt.target.args], stmt.expr)
        return
    stmt.label = st.label
    stmt.file = st.file
    stmt.line = st.line
    if st.label is not None:
        unit.labels[st.label] = len(unit.code)
    unit.code.append(stmt)


def parse_file(path):
    stmts = expand_includes(scan_file(path).statements, os.path.dirname(os.path.abspath(path)))
    errors = []
    units = parse_units(stmts, on_error=lambda st, msg: errors.append((st, msg)))
    return units, errors


def parse_program(root):
    # PATH.FOR is a stale prototype: its PATH (3-entry OK) shadows the canonical
    # PATH.MAC built-in, and its TEST3/TEST4 collide with the real ones in 2.FOR.
    # Exclude it -- PATH is a built-in; TEST3/TEST4 live in 2.FOR.
    files = sorted(
        f
        for f in glob.glob(os.path.join(root, "*.FOR"))
        if os.path.basename(f).upper() != "PATH.FOR"
    )
    all_units = {}
    all_errors = []
    per_file = {}
    for path in files:
        units, errors = parse_file(path)
        per_file[os.path.basename(path)] = (units, errors)
        for u in units:
            all_units[u.name] = u
        all_errors.extend(errors)
    return all_units, all_errors, per_file
