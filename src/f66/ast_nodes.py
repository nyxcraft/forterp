"""AST node definitions for the FORTRAN-10 subset used by Empire.

Expressions and executable statements are dataclasses.  Program-unit-level
declaration information (types, arrays, commons, parameters, data, formats)
lives on ProgramUnit rather than as statement nodes, because the executor runs
a flat statement list with a label table + DO-stack (FORTRAN's arbitrary GOTOs
into/out of "blocks" make a nested-block AST counterproductive).
"""

from __future__ import annotations

from dataclasses import dataclass, field


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
class Complex:                # complex constant (re, im) -- V5 Ch4
    re: object
    im: object

@dataclass
class StrLit:
    value: str            # raw characters; packed to a word at eval time

@dataclass
class LogicalLit:
    value: bool

@dataclass
class Var:
    name: str             # scalar variable / bare function name

@dataclass
class Ref:
    name: str             # NAME(args): array element OR function call
    args: list            # list of expression nodes

@dataclass
class Unary:
    op: str               # 'NOT' | '-' | '+'
    operand: object

@dataclass
class Binary:
    op: str               # OR AND EQ NE LT LE GT GE + - * / ^
    left: object
    right: object


# ----------------------------------------------------------------- statements
@dataclass
class Stmt:
    label: int | None = None
    file: str = ""
    line: int = 0

@dataclass
class Assign(Stmt):
    target: object = None         # Var or Ref
    expr: object = None

@dataclass
class Goto(Stmt):
    target: int = 0

@dataclass
class CompGoto(Stmt):
    labels: list = field(default_factory=list)
    index: object = None

@dataclass
class AssignLabel(Stmt):         # ASSIGN <label> TO <var>  (tgt avoids Stmt.label)
    tgt: int = 0
    var: str = ""

@dataclass
class AssignedGoto(Stmt):        # GO TO <var> [,(label-list)]
    var: str = ""
    labels: list = field(default_factory=list)

@dataclass
class IfLogical(Stmt):
    cond: object = None
    stmt: object = None           # embedded statement

@dataclass
class IfBranch(Stmt):
    """Arithmetic IF (3 labels) or logical two-way IF (2 labels)."""
    cond: object = None
    labels: list = field(default_factory=list)

@dataclass
class Do(Stmt):
    var: str = ""
    start: object = None
    stop: object = None
    step: object = None           # may be None -> 1
    term_label: int = 0

@dataclass
class Continue(Stmt):
    pass

@dataclass
class EntryStmt(Stmt):           # ENTRY name(args) -- alternate subprogram entry point
    name: str = ""
    params: list = field(default_factory=list)

@dataclass
class EncDec(Stmt):              # ENCODE/DECODE(count, fmt, buf) iolist -- internal fmt I/O
    decode: bool = False
    count: object = None
    fmt: object = None
    buf: object = None
    items: list = field(default_factory=list)

@dataclass
class Call(Stmt):
    name: str = ""
    args: list = field(default_factory=list)

@dataclass
class Return(Stmt):
    expr: object = None          # RETURN e  -> alternate (multiple) return

@dataclass
class LabelArg:                  # $nnn / *nnn actual arg = alternate-return target
    label: int = 0

@dataclass
class StopStmt(Stmt):
    code: object = None

@dataclass
class PauseStmt(Stmt):           # PAUSE [n] -- print and continue (batch behavior)
    code: object = None

@dataclass
class TypeStmt(Stmt):             # TYPE fmt, iolist  (terminal output)
    fmt: object = None            # label int, or '*'
    items: list = field(default_factory=list)

@dataclass
class AcceptStmt(Stmt):           # ACCEPT fmt, iolist  (terminal input)
    fmt: object = None
    items: list = field(default_factory=list)
    reread: bool = False          # REREAD: re-parse the last input record

@dataclass
class IoStmt(Stmt):               # READ/WRITE (unit[,fmt][,specs]) iolist
    mode: str = ""                # 'READ' | 'WRITE'
    unit: object = None
    fmt: object = None            # label int, '*', or None (unformatted)
    specs: dict = field(default_factory=dict)   # e.g. {'END': 450}
    items: list = field(default_factory=list)

@dataclass
class FileCtl(Stmt):              # OPEN/CLOSE/REWIND (specs...)
    verb: str = ""
    specs: dict = field(default_factory=dict)

@dataclass
class DefineFile(Stmt):           # DEFINE FILE u(m,n,U,v) [,...] (V5 10.3.5)
    defs: list = field(default_factory=list)   # [{unit,maxrec,recsize,assoc}, ...]

@dataclass
class ImpliedDo:                  # io-list element: ( items, var=e1,e2[,e3] )
    items: list
    var: str
    start: object
    stop: object
    step: object


# --------------------------------------------------------------- program unit
@dataclass
class ProgramUnit:
    kind: str                     # 'program' | 'subroutine' | 'function'
    name: str
    params: list = field(default_factory=list)
    ret_type: str | None = None   # for typed functions
    implicit: dict = field(default_factory=dict)   # letter -> type
    types: dict = field(default_factory=dict)      # name -> type
    arrays: dict = field(default_factory=dict)     # name -> [(lo,hi), ...]
    consts: dict = field(default_factory=dict)     # PARAMETER name -> value
    commons: list = field(default_factory=list)    # (block, [(name,dims)])
    data: list = field(default_factory=list)       # (targets, values)
    externals: set = field(default_factory=set)
    formats: dict = field(default_factory=dict)    # label -> raw format text
    code: list = field(default_factory=list)       # executable Stmt list
    labels: dict = field(default_factory=dict)     # label -> index into code
    stmt_funcs: dict = field(default_factory=dict)  # name -> ([param,...], expr)
    namelists: dict = field(default_factory=dict)  # NAMELIST group -> [item nodes] (V5 Ch11)
    equivs: list = field(default_factory=list)     # EQUIVALENCE groups: [[(name,[subs]),...],...]
