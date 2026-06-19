"""Interactive immediate-mode FORTRAN (a REPL) for the forterp front-ends.

Entered from the command monitor's IMMEDIATE command. Where the monitor operates on
whole files, this runs FORTRAN *statements* as you type them, against a persistent
session:

  * Tier 1 -- a straight-line statement (assignment, I/O, CALL into a LOADed program)
    runs immediately; a bare expression is evaluated and printed, so the prompt doubles
    as a calculator and as a way to inspect a variable by typing its name.
  * Tier 2 -- a DO loop is collected across lines (a continuation prompt) and run as a
    block once its terminator appears.

How it works: the session is a single ProgramUnit whose declarations accumulate as you
type; its UnitRT holds the live variable store. An executable chunk (one statement, or a
DO block) is parsed with those declarations in scope and run by the engine's run_block
primitive against the session UnitRT, so it sees and mutates the same storage -- and
resolves CALLs/refs against any LOADed units. A bare expression is parsed by
parse_expression (same declarations in scope) and evaluated. Declarations rebuild the
engine, carrying the store across. F66 has no incremental-execution model for control
flow, so the unit of work is a statement or a DO block, never a bare GOTO;
COMMON/EQUIVALENCE/NAMELIST need a full program unit (put them in a file and LOAD it).
"""

from __future__ import annotations

import re
import sys

import forterp
from forterp import ast_nodes as A

_TARGETS = {"native": forterp.NATIVE, "pdp10": forterp.PDP10, "vax": forterp.VAX}
_DIALECTS = {"f66": forterp.F66, "fortran10": forterp.FORTRAN10}

SESS = "$REPL"  # name of the session program unit

# Operators whose result is a FORTRAN logical -- so a top-level expression using one is
# shown as .TRUE./.FALSE. rather than the target's raw truth integer (1 / -1).
_LOGICAL_OPS = {"AND", "OR", "XOR", "NEQV", "EQV", "EQ", "NE", "LT", "LE", "GT", "GE"}

# A REPL line is free-form-ish; map it to fixed form so the scanner sees it correctly:
# an optional leading statement label goes in columns 1-5, the statement body in 7+.
_LABEL_RE = re.compile(r"\s*(\d{1,5})\s+(\S.*)$")


def _to_fixed(line):
    """Reposition a typed line into fixed form: `10 CONTINUE` -> label in cols 1-5,
    body at col 7; anything else -> indented to col 7."""
    s = line.rstrip()
    if not s.strip():
        return ""
    m = _LABEL_RE.match(s)
    if m:
        return m.group(1).ljust(5) + " " + m.group(2)
    return "      " + s.strip()


class Immediate:
    """Immediate-mode FORTRAN loop. I/O is injectable for testing (`write`/`errwrite`
    take a string, `readline` returns a line, "" at EOF). `loaded` is an optional
    {name: ProgramUnit} from the monitor's LOAD, so the REPL can call into a program."""

    def __init__(
        self,
        std="f66",
        target="native",
        loaded=None,
        write=None,
        errwrite=None,
        readline=None,
    ):
        self.std = std
        self.target = target
        self.loaded = dict(loaded) if loaded else {}
        self.write = write or sys.stdout.write
        self.errwrite = errwrite or sys.stderr.write
        self.readline = readline or sys.stdin.readline
        self.decls = []  # accumulated declaration source lines (fixed form)
        self.eng = None
        self.sess = None
        self.frame = None
        self._rebuild()

    # ---- the loop ----
    def run(self):
        """Read FORTRAN statements until EXIT / '.' / EOF, then return to the monitor."""
        self.write(
            f"immediate mode ({self.std}) -- type FORTRAN; a bare expression is "
            f"evaluated.  '.' or EXIT returns to the monitor.\n"
        )
        buf, raw = [], []  # fixed-form lines / raw lines of the chunk being collected
        while True:
            self.write("cont> " if buf else f"{self._tag()}* ")
            line = self.readline()
            if line == "":  # EOF -> back to the monitor
                self.write("\n")
                break
            s = line.strip()
            if not buf:
                if not s:
                    continue
                if s == "." or s.upper() in ("EXIT", "QUIT", "MONITOR"):
                    break
            elif not s:  # blank line cancels a half-typed block
                self._err("(block cancelled)")
                buf, raw = [], []
                continue
            buf.append(_to_fixed(line))
            raw.append(line)
            if self._incomplete("\n".join(self.decls + buf)):
                continue  # an open DO -> keep collecting
            self._handle(buf, raw)
            buf, raw = [], []
        return 0

    # ---- classification + dispatch ----
    def _handle(self, buf, raw):
        chunk = "\n".join(buf)
        errs = []
        probe = forterp.parse_source(
            chunk, dialect=self._dialect(), on_error=lambda st, m: errs.append(m)
        )
        u = probe.get("$MAIN")
        if u is not None and u.code:  # executable statement(s) / a DO block
            self._exec(buf)
        elif u is not None and self._has_decl(u):  # a declaration
            self._declare(buf, u, errs)
        else:  # neither -> try it as a bare expression
            self._eval_expr(raw, errs)

    def _exec(self, buf):
        """Run the chunk's statement(s) / DO block against the live session via the
        engine's run_block primitive, which shares the session's store and resolves
        CALLs against any LOADed program."""
        text = "\n".join(self.decls + buf)
        errs = []
        units = forterp.parse_source(
            text, dialect=self._dialect(), on_error=lambda st, m: errs.append(m)
        )
        if errs:
            for m in errs:
                self._err(m)
            return
        u = units.get("$MAIN")
        if u is None or not u.code:
            return
        try:
            self.eng.run_block(self.frame.rt, u.code, u.labels, u.formats)
        except Exception as e:  # a fault returns to the prompt, not a crash
            self._err(f"?{e}")

    def _declare(self, buf, u, errs):
        if errs:
            for m in errs:
                self._err(m)
            return
        if u.commons or u.equivs or u.namelists:  # Tier 3: storage association
            self._err(
                "COMMON/EQUIVALENCE/NAMELIST need a full program unit -- "
                "put them in a file and LOAD it"
            )
            return
        self.decls.extend(buf)
        rebuild_errs = self._rebuild()
        if rebuild_errs:  # roll back a declaration that doesn't combine cleanly
            del self.decls[len(self.decls) - len(buf) :]
            self._rebuild()
            for m in rebuild_errs:
                self._err(m)

    def _eval_expr(self, raw, errs):
        expr = " ".join(r.strip() for r in raw)
        try:  # parse with the session's declarations so A(I) etc. resolve as in-unit
            node = forterp.parse_expression(expr, dialect=self._dialect(), unit=self.sess)
        except Exception:  # not an expression either -> report the statement error
            for m in errs or ["?syntax error"]:
                self._err(m)
            return
        try:
            val = self.eng.eval(node, self.frame)
        except Exception as e:
            self._err(f"?{e}")
            return
        if self._is_logical(node):  # show a truth value as .TRUE./.FALSE.
            self.write((".TRUE." if self.eng.tgt.truthy(val) else ".FALSE.") + "\n")
        else:
            self.write(self._format(val) + "\n")

    # ---- session build / store carry-over ----
    def _rebuild(self):
        """(Re)build the engine from the accumulated declarations, carrying the live
        store across so values survive a declaration. Returns any parse diagnostics."""
        dlc = self._dialect()
        errs = []
        units = forterp.parse_source(
            ("\n".join(self.decls) + "\n"), dialect=dlc, on_error=lambda st, m: errs.append(m)
        )
        sess = units.get("$MAIN") or A.ProgramUnit(kind="program", name=SESS)
        sess.name = SESS
        sess.code, sess.labels = [], {}  # decls only; executables are spliced in transiently
        all_units = dict(self.loaded)
        all_units[SESS] = sess
        eng = forterp.make_engine(
            all_units,
            target=_TARGETS[self.target],
            free_form_input=dlc.free_form_input,
            dec_intrinsics=dlc.dec_intrinsics,
            emit=self.write,
            printer=self.write,
            readline=self.readline,
        )
        if self.eng is not None:  # carry every unit's live store across the rebuild
            for nm, oldrt in self.eng.rts.items():
                if nm in eng.rts:
                    eng.rts[nm].local_scalars.update(oldrt.local_scalars)
                    eng.rts[nm].local_arrays.update(oldrt.local_arrays)
            for b, vals in self.eng.commons.items():
                if b in eng.commons:
                    n = min(len(vals), len(eng.commons[b]))
                    eng.commons[b][:n] = vals[:n]
        self.eng, self.sess = eng, sess
        self.frame = forterp.Frame(eng.rts[SESS], {})
        return errs

    # ---- helpers ----
    def _incomplete(self, text):
        """True while the chunk has a DO whose terminator label hasn't appeared yet."""
        units = forterp.parse_source(text, dialect=self._dialect(), on_error=lambda st, m: None)
        u = units.get("$MAIN")
        if u is None:
            return False
        for i, s in enumerate(u.code):
            if isinstance(s, A.Do):
                j = u.labels.get(s.term_label)
                if j is None or j < i:
                    return True
        return False

    @staticmethod
    def _is_logical(node):
        if isinstance(node, A.Binary):
            return node.op in _LOGICAL_OPS
        if isinstance(node, A.Unary):
            return node.op == "NOT"
        return False

    @staticmethod
    def _has_decl(u):
        return bool(
            u.types
            or u.arrays
            or u.implicit
            or u.consts
            or u.externals
            or u.formats
            or u.data
            or u.stmt_funcs
            or u.commons
            or u.equivs
            or u.namelists
        )

    def _format(self, v):
        if isinstance(v, bool):
            return ".TRUE." if v else ".FALSE."
        if isinstance(v, complex):
            return f"({v.real:g},{v.imag:g})"
        if isinstance(v, float):
            return repr(v)
        return str(v)

    def _tag(self):
        return "f10" if self.std == "fortran10" else "f66"

    def _dialect(self):
        return _DIALECTS[self.std]

    def _err(self, msg):
        self.errwrite(msg + "\n")
