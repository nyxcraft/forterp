"""Debugging + profiling for the interactive front-ends.

A single `Tracer` object is what the engine's per-statement hook (`engine.tracer`) calls
as `tracer(stmt, frame)`. It carries every concern, each independently toggleable, so one
hook serves them all:

  * profiling  -- per-line execution counts (a deterministic cost metric, not wall time)
  * coverage   -- which lines were reached (the same counts, reported as hit/missed)
  * tracing    -- echo each statement as it runs
  * breakpoints + stepping -- pause and drop to an interactive prompt: inspect any
    expression against the paused frame, backtrace, step / next / continue.

A Tracer is installed on the engine (`eng.tracer = t`) only while something is enabled
(`t.active`); a plain run leaves `eng.tracer = None` and pays only a hoisted None check
per statement. The breakpoint prompt reuses the engine's expression evaluator, so
inspecting a variable is just typing its name -- except that a bare command word wins
(typing `N` runs `next`, not "show N", since single-letter vars collide with the command
abbreviations), so `p <expr>` / `print <expr>` / `=<expr>` force inspection.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field

import forterp
import forterp.refs
from forterp import ast_nodes as A

__all__ = [
    # OOB-access census -- public instrumentation for the faithful unchecked-array behavior
    "OobError",
    "OobCensus",
    "oob_census",
    "oob_mode",
    "set_oob_mode",
    "oob_counts",
    "oob_log",
    "clear_oob_log",
    "OOB_MODES",
    # interactive tracer / profiler (driven by the monitor)
    "Tracer",
]


# ---------------------------------------------------------------------------
# Out-of-bounds (OOB) access census
#
# The engine never bounds-checks array/COMMON access -- it reproduces the unchecked PDP-10
# faithfully: an OOB read yields 0, an OOB write is dropped (the 1978 SMAC/ENEMYM overrun
# behavior). This surface lets a tool *observe* that without changing it -- count OOB
# accesses, log each site's context, or (for a checker/fuzzer) turn an OOB into a raise.
# The mode/counters/log live as process-global state in forterp.refs (the memory model);
# this is the public façade over it, so callers never reach into those internals.
# ---------------------------------------------------------------------------

OobError = forterp.refs.OobError  #: raised on an OOB access while the mode is "raise"
OOB_MODES = ("off", "log", "raise")  #: off = silent (faithful); log = census; raise = halt


def oob_mode():
    """The current OOB-check mode -- one of `OOB_MODES`."""
    return forterp.refs.OOB_CHECK


def set_oob_mode(mode):
    """Set the OOB-check mode: 'off' (silent, the faithful default), 'log' (record every OOB
    site and continue), or 'raise' (raise `OobError` on the first OOB)."""
    if mode not in OOB_MODES:
        raise ValueError(f"OOB mode must be one of {OOB_MODES}, not {mode!r}")
    forterp.refs.OOB_CHECK = mode


def oob_counts():
    """Cumulative `(reads, writes)` OOB cell accesses since the process started."""
    return (forterp.refs.OOB_READS, forterp.refs.OOB_WRITES)


def oob_log():
    """The per-site OOB records captured while the mode was 'log'. Each is a dict
    `{op, routine, array, subs, idx, len}` (best-effort context for that access)."""
    return list(forterp.refs.OOB_LOG)


def clear_oob_log():
    """Discard the accumulated per-site OOB log."""
    forterp.refs.OOB_LOG.clear()


@dataclass
class OobCensus:
    """Result of an `oob_census()` block: the OOB reads/writes that occurred during it and,
    in 'log' mode, the per-site records captured during it."""

    reads: int = 0
    writes: int = 0
    sites: list = field(default_factory=list)


@contextmanager
def oob_census(mode="log"):
    """Census out-of-bounds cell accesses within the block, restoring the prior mode on exit.

    Yields an `OobCensus`; on exit its `.reads` / `.writes` hold the counts that occurred
    during the block and `.sites` the per-site records captured during it (when
    `mode == "log"`). The faithful OOB behavior (read -> 0, write dropped) is unchanged --
    this only observes it::

        import forterp, forterp.debug
        with forterp.debug.oob_census() as census:
            forterp.fortran10.run_source(src)
        print(census.reads, census.writes, census.sites)
    """
    eng = forterp.refs
    prev, r0, w0, n0 = eng.OOB_CHECK, eng.OOB_READS, eng.OOB_WRITES, len(eng.OOB_LOG)
    set_oob_mode(mode)
    census = OobCensus()
    try:
        yield census
    finally:
        eng.OOB_CHECK = prev
        census.reads = eng.OOB_READS - r0
        census.writes = eng.OOB_WRITES - w0
        census.sites = list(eng.OOB_LOG[n0:])


# Operators whose result is a FORTRAN logical -> show .TRUE./.FALSE. rather than 1/-1.
_LOGICAL_OPS = {"AND", "OR", "XOR", "NEQV", "EQV", "EQ", "NE", "LT", "LE", "GT", "GE"}


def is_logical(node):
    """Whether `node` is a top-level logical-valued expression (relational/logical op)."""
    if isinstance(node, A.Binary):
        return node.op in _LOGICAL_OPS
    if isinstance(node, A.Unary):
        return node.op == "NOT"
    return False


def format_value(val, node, tgt):
    """Render an evaluated value for display: logicals as .TRUE./.FALSE., complex as
    (re,im), floats via repr, else str. Shared by the REPL and the debugger inspector."""
    if is_logical(node):
        return ".TRUE." if tgt.truthy(val) else ".FALSE."
    if isinstance(val, bool):
        return ".TRUE." if val else ".FALSE."
    if isinstance(val, complex):
        return f"({val.real:g},{val.imag:g})"
    if isinstance(val, float):
        return repr(val)
    return str(val)


class Tracer:
    """Per-statement debug/profile hook for one engine. I/O is injectable for testing."""

    def __init__(self, write, readline, errwrite=None, dialect=None):
        self.write = write
        self.readline = readline
        self.errwrite = errwrite or write
        self.dialect = dialect or forterp.F66
        self.eng = None  # set by the front-end before each run
        self.units = {}  # the units that ran (for the coverage report)
        # profiling / coverage
        self.profiling = False
        self.counts = {}  # (unit_name, line) -> times executed
        # tracing
        self.tracing = False
        # breakpoints / stepping
        self.breaks = set()  # statement lines to stop at
        self.stepping = False  # stop at the next statement
        self._step_depth = None  # 'next' (step over): only pause when frames <= this

    @property
    def active(self):
        """Whether any feature is on -- the front-end installs us only when True."""
        return self.profiling or self.tracing or bool(self.breaks) or self.stepping

    def start_run(self, eng, units):
        """Bind to a freshly built engine and reset per-run profile data."""
        self.eng = eng
        self.units = units
        self.counts = {}

    # ---- the per-statement hook the engine calls ----
    def __call__(self, stmt, frame):
        if self.profiling:
            key = (frame.rt.unit.name, stmt.line)
            self.counts[key] = self.counts.get(key, 0) + 1
        if self.tracing:
            self.write(f"  {frame.rt.unit.name}:{stmt.line}  {type(stmt).__name__}\n")
        if self._should_pause(stmt):
            self._pause(stmt, frame)

    def _should_pause(self, stmt):
        if stmt.line in self.breaks:
            return True
        if self.stepping:
            return self._step_depth is None or len(self.eng.frames) <= self._step_depth
        return False

    # ---- the interactive breakpoint prompt ----
    def _pause(self, stmt, frame):
        self.stepping = False  # consume the pending step; a command may re-arm it
        self._step_depth = None
        self.write(f"-- stopped at {frame.rt.unit.name}:{stmt.line} ({type(stmt).__name__})\n")
        while True:
            self.write("(dbg) ")
            try:
                line = self.readline()
            except EOFError:  # Ctrl-D via an input()-style reader -> treat as EOF
                line = ""
            except KeyboardInterrupt:  # ^C at the debugger prompt: re-prompt, don't crash
                self.write("\n")
                continue
            if line == "":  # EOF (Ctrl-D) -> detach and continue running
                self.write("\n")
                return
            cmd = line.strip()
            if not cmd:
                continue
            word, _, arg = cmd.partition(" ")
            word, arg = word.lower(), arg.strip()

            # Commands that RESUME the run -- each returns from _pause.
            if word in ("c", "cont", "continue"):
                return
            if word in ("s", "step"):  # stop at the very next statement
                self.stepping, self._step_depth = True, None
                return
            if word in ("n", "next"):  # step over calls: pause in this frame or shallower
                self.stepping, self._step_depth = True, len(self.eng.frames)
                return

            # Everything else acts and STAYS at the prompt (loop again).
            self._prompt_command(word, arg, cmd, frame)

    def _prompt_command(self, word, arg, cmd, frame):
        """Run one breakpoint-prompt command that does NOT resume the run -- inspection,
        breakpoint edits, backtrace/list, or quit. (Resuming commands are handled inline
        in `_pause` so they can return from it.)"""
        if cmd[0] == "=":  # `=expr` -> force inspect (escape for a command-named var)
            self._inspect(cmd[1:].strip(), frame)
        elif word in ("p", "print"):  # explicit inspect (e.g. `p N` for a command-named var)
            self._inspect(arg, frame)
        elif word in ("w", "where", "bt"):
            self._backtrace()
        elif word in ("b", "break"):
            self.add_break(arg)
        elif word in ("d", "delete", "unbreak"):
            self.remove_break(arg)
        elif word in ("l", "list"):
            self._list(frame)
        elif word in ("q", "quit"):
            raise forterp.engine.StopExecution()  # abort the run, return to the monitor
        else:  # anything else: evaluate it against the paused frame
            self._inspect(cmd, frame)

    def _inspect(self, text, frame):
        try:
            node = forterp.parser.parse_expression(text, dialect=self.dialect, unit=frame.rt.unit)
            val = self.eng.eval(node, frame)
        except forterp.engine.StopExecution:
            raise  # a STOP reached while inspecting aborts the run; don't swallow it
        except Exception as e:
            self.errwrite(f"?{e}\n")
            return
        self.write(format_value(val, node, self.eng.tgt) + "\n")

    def _backtrace(self):
        for i, (name, line) in enumerate(reversed(self.eng.backtrace())):  # innermost first
            self.write(f"  #{i} {name}:{line}\n")

    def _list(self, frame):
        code = frame.rt.unit.code
        for j in range(max(0, frame.pc - 2), min(len(code), frame.pc + 3)):
            mark = "->" if j == frame.pc else "  "
            self.write(f"  {mark} {code[j].line}: {type(code[j]).__name__}\n")

    def add_break(self, arg):
        if not arg:
            self.write(f"  breakpoints: {sorted(self.breaks) or '(none)'}\n")
            return
        try:
            self.breaks.add(int(arg))
            self.write(f"  break at line {int(arg)}\n")
        except ValueError:
            self.errwrite("break: a line number is expected\n")

    def remove_break(self, arg):
        if not arg:
            self.breaks.clear()
            self.write("  all breakpoints cleared\n")
            return
        try:
            self.breaks.discard(int(arg))
        except ValueError:
            self.errwrite("unbreak: a line number is expected\n")

    # ---- reports (called by the front-end after a run) ----
    def profile_report(self, top=15):
        if not self.counts:
            return "(no profile data -- PROFILE ON, then RUN)"
        items = sorted(self.counts.items(), key=lambda kv: (-kv[1], kv[0]))[:top]
        rows = ["   count  location"] + [f"  {c:6d}  {n}:{ln}" for (n, ln), c in items]
        return "\n".join(rows)

    def coverage_report(self):
        if not self.counts:
            return "(no coverage data -- PROFILE ON, then RUN)"
        rows = []
        for name, u in self.units.items():
            all_lines = {s.line for s in u.code}
            if not all_lines:
                continue
            hit = {ln for (n, ln) in self.counts if n == name}
            missed = sorted(all_lines - hit)
            tail = f"  missed: {missed}" if missed else "  (full)"
            rows.append(f"  {name}: {len(hit)}/{len(all_lines)} lines{tail}")
        return "\n".join(rows) or "(no coverage data)"
