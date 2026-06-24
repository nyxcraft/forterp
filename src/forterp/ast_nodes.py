"""AST node definitions for FORTRAN-66 / DEC FORTRAN-10.

Expressions and executable statements are dataclasses.  Program-unit-level
declaration information (types, arrays, commons, parameters, data, formats)
lives on ProgramUnit rather than as statement nodes, because the executor runs
a flat statement list with a label table + DO-stack (FORTRAN's arbitrary GOTOs
into/out of "blocks" make a nested-block AST counterproductive).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Union

# --- type aliases: the contracts the parser produces and the engine consumes ------
# `from __future__ import annotations` keeps field annotations lazy (strings), so these
# document intent for readers/tooling at no import-time cost. There is no static checker
# in the build; they are precise documentation, not enforced types.
Expr = Union[
    "IntLit",
    "RealLit",
    "OctalLit",
    "Complex",
    "StrLit",
    "LogicalLit",
    "Var",
    "Ref",
    "Unary",
    "Binary",
]
IoItem = Union[Expr, "ImpliedDo"]  # an I/O list element: an expression or an implied-DO
FormatRef = Union[int, str, None]  # FORMAT label, '*' (list-directed), or None (unformatted)
Dims = list[tuple[int, int]]  # array bounds: [(lo, hi), ...]


# ---------------------------------------------------------------- expressions
@dataclass
class IntLit:
    value: int


@dataclass
class RealLit:
    value: float


@dataclass
class OctalLit:
    value: int


@dataclass
class Complex:  # complex constant (re, im) -- V5 Ch4
    re: Expr
    im: Expr


@dataclass
class StrLit:
    value: str  # raw characters; packed to a word at eval time


@dataclass
class LogicalLit:
    value: bool


@dataclass
class Var:
    name: str  # scalar variable / bare function name


@dataclass
class Ref:
    name: str  # NAME(args): array element OR function call
    args: list[Expr]


@dataclass
class Unary:
    op: str  # 'NOT' | '-' | '+'
    operand: Expr


@dataclass
class Binary:
    op: str  # OR AND EQ NE LT LE GT GE + - * / ^
    left: Expr
    right: Expr


# ----------------------------------------------------------------- statements
@dataclass
class Stmt:
    label: Optional[int] = None
    file: str = ""
    line: int = 0


@dataclass
class Assign(Stmt):
    target: Optional[Expr] = None  # Var or Ref
    expr: Optional[Expr] = None


@dataclass
class Goto(Stmt):
    target: int = 0


@dataclass
class CompGoto(Stmt):
    labels: list[int] = field(default_factory=list)
    index: Optional[Expr] = None


@dataclass
class AssignLabel(Stmt):  # ASSIGN <label> TO <var>  (tgt avoids Stmt.label)
    tgt: int = 0
    var: str = ""


@dataclass
class AssignedGoto(Stmt):  # GO TO <var> [,(label-list)]
    var: str = ""
    labels: list[int] = field(default_factory=list)


@dataclass
class IfLogical(Stmt):
    cond: Optional[Expr] = None
    stmt: Optional[Stmt] = None  # embedded statement


@dataclass
class IfBranch(Stmt):
    """Arithmetic IF (3 labels) or logical two-way IF (2 labels)."""

    cond: Optional[Expr] = None
    labels: list[int] = field(default_factory=list)


@dataclass
class Do(Stmt):
    var: str = ""
    start: Optional[Expr] = None
    stop: Optional[Expr] = None
    step: Optional[Expr] = None  # may be None -> 1
    term_label: int = 0


@dataclass
class Continue(Stmt):
    pass


# Structured-block markers (F77 / FORTRAN-10). These are transient: the parser emits them,
# then `_lower_structured` rewrites each construct into IfLogical/Goto/Continue with synthetic
# labels, so they never reach the engine. Block IF nests via the existing flat label+GOTO model.
@dataclass
class BlockIf(Stmt):  # IF (cond) THEN
    cond: Optional[Expr] = None


@dataclass
class ElseIf(Stmt):  # ELSE IF (cond) THEN
    cond: Optional[Expr] = None


@dataclass
class Else(Stmt):  # ELSE
    pass


@dataclass
class EndIf(Stmt):  # END IF / ENDIF
    pass


@dataclass
class DoWhile(Stmt):  # DO WHILE (cond)
    cond: Optional[Expr] = None


@dataclass
class EndDo(Stmt):  # END DO / ENDDO
    pass


@dataclass
class EntryStmt(Stmt):  # ENTRY name(args) -- alternate subprogram entry point
    name: str = ""
    params: list[str] = field(default_factory=list)


@dataclass
class EncDec(Stmt):  # ENCODE/DECODE(count, fmt, buf) iolist -- internal fmt I/O
    decode: bool = False
    count: Optional[Expr] = None
    fmt: FormatRef = None
    buf: Optional[Expr] = None
    items: list[IoItem] = field(default_factory=list)


@dataclass
class Call(Stmt):
    name: str = ""
    args: list[Expr] = field(default_factory=list)


@dataclass
class Return(Stmt):
    expr: Optional[Expr] = None  # RETURN e  -> alternate (multiple) return


@dataclass
class LabelArg:  # $nnn / *nnn actual arg = alternate-return target
    label: int = 0


@dataclass
class StopStmt(Stmt):
    code: Optional[Expr] = None


@dataclass
class PauseStmt(Stmt):  # PAUSE [n] -- print and continue (batch behavior)
    code: Optional[Expr] = None


@dataclass
class TypeStmt(Stmt):  # TYPE fmt, iolist  (terminal output)
    fmt: FormatRef = None  # label int, or '*'
    items: list[IoItem] = field(default_factory=list)


@dataclass
class AcceptStmt(Stmt):  # ACCEPT fmt, iolist  (terminal input)
    fmt: FormatRef = None
    items: list[IoItem] = field(default_factory=list)
    reread: bool = False  # REREAD: re-parse the last input record


@dataclass
class IoStmt(Stmt):  # READ/WRITE (unit[,fmt][,specs]) iolist
    mode: str = ""  # 'READ' | 'WRITE'
    unit: Optional[Expr] = None
    fmt: FormatRef = None  # label int, '*', or None (unformatted)
    specs: dict[str, object] = field(default_factory=dict)  # e.g. {'END': 450}
    items: list[IoItem] = field(default_factory=list)


@dataclass
class FileCtl(Stmt):  # OPEN/CLOSE/REWIND (specs...)
    verb: str = ""
    specs: dict[str, object] = field(default_factory=dict)


@dataclass
class DefineFile(Stmt):  # DEFINE FILE u(m,n,U,v) [,...] (V5 10.3.5)
    defs: list[dict] = field(default_factory=list)  # [{unit,maxrec,recsize,assoc}, ...]


@dataclass
class ImpliedDo:  # io-list element: ( items, var=e1,e2[,e3] )
    items: list[IoItem]
    var: str
    start: Expr
    stop: Expr
    step: Optional[Expr]


# --------------------------------------------------------------- program unit
@dataclass
class ProgramUnit:
    kind: str  # 'program' | 'subroutine' | 'function'
    name: str
    params: list[str] = field(default_factory=list)
    ret_type: Optional[str] = None  # for typed functions
    implicit: dict[str, str] = field(default_factory=dict)  # letter -> type
    types: dict[str, str] = field(default_factory=dict)  # name -> type
    arrays: dict[str, Dims] = field(default_factory=dict)  # name -> [(lo,hi), ...]
    consts: dict[str, object] = field(default_factory=dict)  # PARAMETER name -> value
    commons: list[tuple[str, list]] = field(default_factory=list)  # (block, [(name, dims)])
    data: list[tuple] = field(default_factory=list)  # (targets, values)
    externals: set[str] = field(default_factory=set)
    formats: dict[int, str] = field(default_factory=dict)  # label -> raw format text
    code: list[Stmt] = field(default_factory=list)  # executable Stmt list
    labels: dict[int, int] = field(default_factory=dict)  # label -> index into code
    stmt_funcs: dict[str, tuple] = field(default_factory=dict)  # name -> ([param, ...], expr)
    namelists: dict[str, list] = field(default_factory=dict)  # group -> [item nodes] (V5 Ch11)
    equivs: list[list] = field(default_factory=list)  # EQUIVALENCE groups [[(name,[subs]),...],...]
