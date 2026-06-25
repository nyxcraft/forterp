"""Execution engine + value model for the forterp FORTRAN-66 / DEC FORTRAN-10 interpreter.

Value model (configurable via the Engine's Target; the PDP10 target is described here):
  * every word is a Python int held in signed 36-bit range, or a float for REAL.
  * character/Hollerith literals -> left-justified blank-padded packed ASCII,
    interpreted as a *signed* 36-bit int (matching PDP-10 CAM comparisons).
Memory model:
  * COMMON blocks are flat word arrays with storage association (a unit's
    variables map onto offsets, so different units overlay the same words).
  * locals are static per unit (FORTRAN-10 allocated them statically -- they
    persist across calls), arguments are passed by reference.
Control model:
  * each unit runs as a flat statement list with a program counter, a label
    table, and a DO-stack (FORTRAN's arbitrary GOTOs make this the right shape).
"""

from __future__ import annotations

import cmath
import itertools
import math

from forterp import ast_nodes as A
from forterp.target import NATIVE, PDP10

# The default target's value model (see target.py), re-exported as module-level names:
# forlib, the intrinsics table, the empire builtins and tests import these. The Engine
# routes its OWN value model through self.tgt; these aliases are the PDP-10 default.
MASK36 = PDP10.mask
SIGN36 = PDP10.sign
wrap36 = PDP10.wrap


def trunc_div(a: int, b: int) -> int:
    if b == 0:
        return 0  # FORTRAN-10/FOROTS warned on divide-by-zero and CONTINUED
        #                   (non-fatal, quotient 0); never aborted like Python. The
        #                   exact recovery value is moot -- what matters is FOROTS-style
        #                   warn-and-continue, not crashing the interpreter.
    q = abs(a) // abs(b)
    return q if (a < 0) == (b < 0) else -q


def fort_mod(a, b):
    if b == 0:
        return a  # quotient 0 on divide-by-zero -> a - 0*b = a (non-fatal)
    if isinstance(a, float) or isinstance(b, float):
        return a - b * float(int(a / b))
    return a - b * trunc_div(a, b)


truthy = PDP10.truthy  # FORTRAN-10: .TRUE. iff sign negative (-1/0)
packword = PDP10.pack  # chars -> one signed packed word

# I/O status as the (ERRSNS status code, FOROTS monitor code) pair that `last_io_error`
# holds and ERRSNS reports (V5 App H). Named so the I/O paths carry no bare magic numbers.
IO_OK = (0, 0)  # success / status cleared
IO_EOF = (24, 308)  # end-of-file on input
IO_BAD_RECORD = (25, 302)  # invalid or unwritten (random-access) record
IO_ILLEGAL_CHAR = (38, 311)  # illegal character in formatted input


# ----------------------------------------------------------------- references
#: counts faithful out-of-bounds cell accesses (FORTRAN-10 had no array bounds
#: checking; OOB touched adjacent memory). Per-process; tools snapshot the delta.
OOB_READS = 0
OOB_WRITES = 0

#: OOB handling mode. "off" = faithful silent (read->0, write->drop, matching the
#: unchecked PDP-10). "log" = also append full context to OOB_LOG and continue (an
#: audit/checker mode for fuzzing: surfaces every OOB so program-bug edges can be told
#: apart from interpreter bugs). "raise" = hard error (fail-fast strict checker).
OOB_CHECK = "off"
OOB_LOG = []  # populated when OOB_CHECK == "log"


class OobError(Exception):
    """Raised on an out-of-bounds cell access when OOB_CHECK == 'raise'."""


def _oob_context(idx, store_len, op):
    """Best-effort (routine, array, subscripts) for an OOB, via the eval stack."""
    import inspect

    routine = array = subs = None
    for fi in inspect.stack()[2:]:
        loc = fi.frame.f_locals
        fr = loc.get("frame")
        nm = getattr(getattr(getattr(fr, "rt", None), "unit", None), "name", None)
        if nm and routine is None:
            routine = nm
        if array is None and "name" in loc and "subs" in loc:
            array, subs = loc.get("name"), list(loc.get("subs"))
        if routine and array is not None:
            break
    return {
        "op": op,
        "routine": routine,
        "array": array,
        "subs": subs,
        "idx": idx,
        "len": store_len,
    }


def _oob_event(idx, store_len, op):
    if OOB_CHECK == "raise":
        raise OobError(_oob_context(idx, store_len, op))
    if OOB_CHECK == "log":
        OOB_LOG.append(_oob_context(idx, store_len, op))


def oob_read(store, idx):
    """Read store[idx] with FORTRAN-10's unchecked-pointer semantics: an out-of-bounds (or
    negative) index reads 0 rather than faulting. The single source of that rule -- CellRef
    and the engine's scalar/array fast paths all go through here (no per-access object)."""
    if 0 <= idx < len(store):
        return store[idx]
    global OOB_READS
    OOB_READS += 1
    if OOB_CHECK != "off":
        _oob_event(idx, len(store), "read")
    return 0


def oob_write(store, idx, v):
    """Write store[idx] with FORTRAN-10's unchecked-pointer semantics: an out-of-bounds (or
    negative) index is dropped rather than faulting. The write counterpart of oob_read."""
    if 0 <= idx < len(store):
        store[idx] = v
        return
    global OOB_WRITES
    OOB_WRITES += 1
    if OOB_CHECK != "off":
        _oob_event(idx, len(store), "write")


class CellRef:
    """Reference to one word in a backing list.

    FORTRAN-10 compiled array access as unchecked pointer arithmetic, so an
    out-of-bounds reference read/wrote adjacent memory rather than faulting (e.g.
    KLINE's FOO(0:3) indexed at 4/5 when an unclamped sector number is 8/9). We
    model that faithfully: OOB read -> 0 (benign garbage), OOB write -> dropped.
    Negative indices are treated as OOB too (no Python end-wrap)."""

    __slots__ = ("store", "idx")

    def __init__(self, store, idx):
        self.store, self.idx = store, idx

    def read(self):
        return oob_read(self.store, self.idx)

    def write(self, v):
        oob_write(self.store, self.idx, v)


class DictRef:
    """Reference to a named local scalar (lazily defaulting to 0)."""

    __slots__ = ("d", "key")

    def __init__(self, d, key):
        self.d, self.key = d, key

    def read(self):
        return self.d.get(self.key, 0)

    def write(self, v):
        self.d[self.key] = v


class TempRef:
    """Reference to a pass-by-value temporary."""

    __slots__ = ("val",)

    def __init__(self, val):
        self.val = val

    def read(self):
        return self.val

    def write(self, v):
        self.val = v


class SubstringRef:
    """Writable reference to a CHARACTER substring lvalue S(lo:hi) (1-based, inclusive).
    read() returns the slice; write() splices the value (fitted to the substring width) back
    into the base, preserving its declared length -- so a substring can be an I/O-list item or
    an actual argument, not just an assignment target."""

    __slots__ = ("base", "lo", "hi", "n")

    def __init__(self, base, lo, hi, n):
        self.base, self.lo, self.hi, self.n = base, lo, hi, n

    def _cur(self):
        cur = self.base.read()
        return cur.ljust(self.n)[: self.n] if isinstance(cur, str) else " " * self.n

    def read(self):
        return self._cur()[self.lo - 1 : self.hi]

    def write(self, v):
        cur = self._cur()
        width = max(self.hi - self.lo + 1, 0)
        s = str(v)[:width].ljust(width)
        self.base.write((cur[: self.lo - 1] + s + cur[self.hi :])[: self.n].ljust(self.n))


class ProcRef:
    """A procedure name passed as an actual argument (F66 8.3/15.10: a dummy
    procedure). Bound to a dummy parameter, it makes CALL <dummy>(...) or a
    function reference dispatch to the named external procedure."""

    __slots__ = ("target",)

    def __init__(self, target):
        self.target = target

    def read(self):  # if used as a value, it's just the name
        return self.target


class ArrayView:
    """A view onto a backing store at a base offset; .loc(i) -> CellRef."""

    __slots__ = ("store", "base")

    def __init__(self, store, base):
        self.store, self.base = store, base

    def loc(self, i):
        return CellRef(self.store, self.base + i)


def linidx(subs, dims):
    """Column-major linear index from subscripts and (lo,hi) dimension list."""
    idx, mult = 0, 1
    for k, (lo, hi) in enumerate(dims):
        idx += (subs[k] - lo) * mult
        mult *= hi - lo + 1
    return idx


def array_size(dims):
    n = 1
    for lo, hi in dims:
        n *= hi - lo + 1
    return n


# ------------------------------------------------------------- control signals
class Goto:
    __slots__ = ("label",)

    def __init__(self, label):
        self.label = label


class Ret:
    __slots__ = ("alt",)

    def __init__(self, alt=None):
        self.alt = alt  # RETURN e -> alternate return


class Stop:
    pass


# --------------------------------------------------------------------- frames
class DoFrame:
    __slots__ = ("ref", "trips", "step", "term", "body", "term_idx")

    def __init__(self, ref, trips, step, term, body, term_idx):
        self.ref, self.trips, self.step, self.term = ref, trips, step, term
        self.body = body  # pc of first statement inside the loop
        self.term_idx = term_idx  # pc of the loop's terminal statement


class Frame:
    __slots__ = ("rt", "args", "pc", "do_stack", "do_suspended")

    def __init__(self, rt, args):
        self.rt = rt
        self.args = args  # dummy name -> Ref / ArrayView
        self.pc = 0
        self.do_stack = []
        # DO loops left via a GO TO out of their range, kept in case control jumps back
        # in -- F66 7.1.2.8.2 "extended range". See run()'s GO TO handling.
        self.do_suspended = []


# --------------------------------------------------------------- unit runtime
class UnitRT:
    def __init__(self, unit):
        self.unit = unit
        self.common_map = {}  # name -> (block, offset, dims|None)
        self.local_scalars = {}  # static
        self.local_arrays = {}  # name -> store(list)
        self.do_terms = set()  # labels that terminate some DO
        self.assigned = set()  # names used as scalar lvalues -> local vars
        for s in unit.code:
            if isinstance(s, A.Do):
                self.do_terms.add(s.term_label)
            self._scan_assigned(s)

    def _scan_assigned(self, s):
        """Collect scalar names that are assignment / DO / input targets, so a
        bare name like FGHT's local `H` isn't mistaken for FUNCTION H()."""
        t = type(s)
        if t is A.Assign and isinstance(s.target, A.Var):
            self.assigned.add(s.target.name)
        elif t is A.Do:
            self.assigned.add(s.var)
        elif t is A.IfLogical and s.stmt is not None:
            self._scan_assigned(s.stmt)
        elif t in (A.AcceptStmt, A.IoStmt):
            for it in s.items:
                if isinstance(it, A.Var):
                    self.assigned.add(it.name)


DEFAULT_INT_LETTERS = set("IJKLMN")

# Default value of the clock provider (eng.now), as (Y, M, D, hh, mm, ss, tenth).
# A FIXED timestamp so every automated harness (tests/fuzz/autoplay/replay) is
# deterministic; the interactive driver overrides eng.now with a real clock.
DEFAULT_CLOCK = (1979, 1, 1, 0, 0, 0, 0)


class Engine:
    # Debug/profile seam, kept as CLASS defaults so a normal engine's instance __dict__ is
    # unchanged (adding these in __init__ measurably slowed every self.* access in the hot
    # loop -- ~8% on a tight loop). `tracer`, if set on an instance, is called per statement
    # (see forterp.debug); `frames` is the active call chain, materialized to a list on the
    # instance only when a debugged/profiled run starts (run()). A plain run never sets either.
    tracer = None
    frames = ()

    def __init__(
        self,
        units: dict,
        root=".",
        emit=None,
        getch=None,
        readline=None,
        set_echo=None,
        set_autowrap=None,
        printer=None,
        target=None,
        binio=None,
        free_form_input=False,
        dec_intrinsics=True,
        character_type=False,
        zero_trip_do=False,
        max_array_words=50_000_000,
        forots=False,
        tty_width=80,
        tty_autowrap=True,
    ):
        from forterp.forlib import Fortran10RNG

        self.tgt = target if target is not None else NATIVE  # default value model (portable)
        self.binio = binio  # unformatted-I/O codec (FOROTS); injected by the runtime
        # `forots`: run under the FORTRAN-10 Object Time System. One flag for the whole FOROTS
        # subsystem -- unformatted files are real FOROTS binary (LSCW records, core-dump bytes,
        # PDP-10 floats) instead of the portable JSON word-list, AND formatted terminal output
        # uses advance-before-print carriage control (see do_type / fmt.apply_carriage_advance).
        # Off by default (portable form + newline-after, unchanged for everyone); make_engine and
        # Interpreter default it ON for the PDP10 target + FORTRAN10 dialect -- real DEC FORTRAN-10,
        # the only case that actually runs through FOROTS. Overridable.
        self.forots = forots
        self._forots_pending = False  # a forots terminal TYPE left a pending advance-before line
        self.monitor = None  # injectable Monitor facade for @uuo (forterp.hostlib);
        # None -> the baseline (tty/files/clock) is built on first use; set it to a richer facade
        # Two dialect-derived knobs the engine needs at run time (else dialect-agnostic):
        #  - free_form_input: widthless input fields read free-form (FORTRAN-10) vs column (F66)
        #  - dec_intrinsics: expose the DEC/F77 extra library functions beyond F66 Tables 3 & 4
        # (default True so a bare Engine has the full library; the dialect paths gate it).
        self.free_form_input = free_form_input
        self.dec_intrinsics = dec_intrinsics
        self.zero_trip_do = zero_trip_do  # F77 zero-trip DO vs F66/DEC one-trip (see exec_do)
        #  - character_type: the F77 CHARACTER data type is in play. A string literal then
        #    evaluates to a Python str (a character constant), not a packed-ASCII Hollerith
        #    word -- so CHARACTER vars/concatenation/comparison work. Off for F66/FORTRAN-10,
        #    which keep the Hollerith packed-int model. (CHARACTER under FORTRAN-10 is future.)
        self.character_type = character_type
        self.units = units
        self.commons = {}  # block -> list (flat store)
        self.rts = {}  # unit name -> UnitRT
        self.entries = {}  # ENTRY name -> (owning unit, pc, params)  (V5 15.7)
        self.builtins = {}
        self.root = root  # base dir for INCLUDE / read-only source + data
        self.save_root = root  # base dir for OPEN file specs (NOT a sandbox -- a
        # driver may point it elsewhere; see _open_path)
        self.out = []  # captured terminal output
        self.rng = Fortran10RNG()  # DEC FORTRAN-10 FORLIB RAN: the Lehmer LCG (V5 Ch15)
        self.clock = 1
        # unit number -> open-file state; the shape depends on its "mode":
        #   "term"      terminal (read via readline, write via emit)
        #   "lpt"       line printer (write via self.printer)
        #   "r" / "w"   sequential file as ordered records {recs, pos, path}; "w"
        #               buffers and serializes on CLOSE. A formatted TEXT file adds
        #               "text": True (records are lines, not value-lists).
        #   "random"    random-access {recs, pos, assoc}, indexed by record number
        self.io = {}
        # FORTRAN-10 V5 Table 10-1 default device assignments: a unit used but never
        # explicitly OPENed routes to a default device -- units 3/6 to the line printer,
        # unit 5 to terminal/card input. The printer and terminal are injected host
        # services (self.printer / readline), so the core stays host-agnostic: an
        # unopened WRITE(6,...) spools, READ(5,...) reads a terminal line.
        self.default_devices = {3: "lpt", 5: "term", 6: "lpt"}
        # FOROTS runtime error status (V5 Appendix H): ERRSNS reports the last
        # I/O op's (first, second) code; ERRSET caps how many LIB/APR domain
        # warnings get printed -- V5 Table 15-3: suppress after N occurrences,
        # default N=2.
        self.last_io_error = IO_OK
        self.errset_limit = 2
        self.lib_apr_count = 0
        self.sense_lights = set()  # SLITE/SLITET console sense lights (V5 Table 15-3)
        # Clock provider -- an ENVIRONMENT SERVICE the driver supplies. The standard
        # library TIME/DATE (forlib.py) read wall time ONLY through this hook, so the
        # language core has no ambient os-time dependency and determinism is an injected
        # input (like the RNG seed). Default = fixed timestamp; an interactive driver
        # overrides it with a real (per-session) clock.
        self.now = lambda: DEFAULT_CLOCK
        # Pluggable OPEN device handlers (devname -> fn(eng, unit, specs, frame)). The
        # core knows only TTY + ordinary files; a host program registers the rest (e.g.
        # a 'GAM:' terrain device) via register_device, so the engine stays host-agnostic.
        self.device_handlers = {}
        self.steps = 0
        self.max_steps = 50_000_000  # bounds compute (runaway loops) -> _budget_error
        # bounds a single array/COMMON allocation so a hostile or accidental huge DIMENSION
        # (e.g. A(2000000000)) raises a clean error instead of OOM-ing the host. Generous;
        # pass max_array_words= to the constructor (it is applied before _build below) or
        # raise eng.max_array_words for a program that legitimately needs more.
        self.max_array_words = max_array_words
        # (tracer / frames are class-level defaults -- see the top of the class -- so a
        # normal run leaves the instance __dict__ identical to the pre-debug engine.)
        # Parsed FORMATs, memoized by spec text. Reusing one parsed object per spec lets
        # an nH/'...' field read on input persist its replacement chars to a later WRITE
        # of the same FORMAT (F66 7.2.3.8) -- and saves re-parsing a hot format each I/O.
        self._fmt_cache = {}
        self._emit = emit or (lambda s: self.out.append(s))
        self._getch = getch
        self._readline = readline
        self._set_echo = set_echo  # front-end hook to change the real terminal echo mode
        self._set_autowrap = set_autowrap  # optional front-end hook, also notified on a change
        self._printer = printer
        # FORTRAN-10 terminal line discipline ('free CR-LF'): emit() inserts a newline at the
        # carriage width so terminal output doesn't overrun the margin. `tty_width` is the carriage
        # width (0 = no wrap); `_autowrap` is the switch a program toggles via TRMOP. .TONFC (our
        # TRMOP2). Active only under the DEC dialect (dec_intrinsics); strict F66 never wraps.
        # `_col` tracks the output column (also read by the tty facade's crlf/tab).
        self._tty_width = tty_width
        self._autowrap = tty_autowrap
        self._col = 0
        self._build()

    # ---- terminal / RNG plumbing
    def emit(self, s):
        # FORTRAN-10 'free CR-LF' (TOPS-10 monitor line discipline): wrap terminal output at the
        # carriage width. Gated on the DEC dialect + the autowrap switch (TRMOP2 / .TONFC disables
        # it for a cursor-addressed full-screen display); strict F66 never wraps. Either way, track
        # the output column so the tty facade's crlf/tab stay accurate.
        if self.dec_intrinsics and self._autowrap and self._tty_width > 0:
            s = self._wrap_cols(s)
        else:
            nl = s.rfind("\n")
            self._col = (len(s) - nl - 1) if nl >= 0 else self._col + len(s)
        self._emit(s)

    def _wrap_cols(self, s):
        """Insert a newline at the carriage margin (free CR-LF) and track the output column.
        Deferred wrap: exactly `_tty_width` printing chars fit on a line; the next one wraps."""
        w = self._tty_width
        col = self._col
        out = []
        for ch in s:
            if ch in "\n\r\f":  # newline / return / form-feed -> back to the left margin
                out.append(ch)
                col = 0
            elif ch == "\t":  # tab advances to the next 8-column stop (passes through)
                out.append(ch)
                col = (col // 8 + 1) * 8
            elif ch == "\b":  # backspace
                out.append(ch)
                col = col - 1 if col > 0 else 0
            elif " " <= ch <= "~":  # a printing char: wrap at the margin, then advance
                if col >= w:
                    out.append("\n")
                    col = 0
                out.append(ch)
                col += 1
            else:  # other control (BEL, ESC, ...): passes through, no column change
                out.append(ch)
        self._col = col
        return "".join(out)

    def getch(self):
        return self._getch() if self._getch else "\n"

    def readline(self):
        return self._readline() if self._readline else ""

    def set_echo(self, on):
        """Change the terminal echo mode through the injected front-end hook (no-op if unwired).
        A program toggles echo for raw single-key input; a front-end that owns a real terminal
        flips its actual echo (its manual line-echo, or a tty's ECHO bit)."""
        if self._set_echo:
            self._set_echo(bool(on))

    def set_autowrap(self, on):
        """Set the terminal autowrap / 'free CR-LF' mode (the PDP-10 TRMOP. .TONFC switch -- our
        TRMOP2). Under the DEC dialect this drives emit()'s own column wrapping, so a program
        disabling it (for a full-screen, cursor-addressed display) stops the margin newline
        host-side -- as TOPS-10's monitor did, no terminal escape needed. An optional front-end
        hook is also notified (e.g. an ANSI renderer that wants ESC[?7l / ESC[?7h)."""
        self._autowrap = bool(on)
        if self._set_autowrap:
            self._set_autowrap(bool(on))

    def printer(self, s):
        # Line-printer (LPT) sink. The driver attaches a spool file; with no driver hook we fall
        # back to the raw output sink (NOT emit) so printer output is never silently lost -- and is
        # not subject to the terminal's free-CR-LF margin wrap (a printer has its own width).
        (self._printer or self._emit)(s)

    def seed_rng(self, n):
        self.rng.seed(n & self.tgt.mask)

    def register_builtins(self, table):
        self.builtins.update(table)

    def register_device(self, name, fn):
        """Register an OPEN device handler. `fn(eng, unit, specs, frame)` sets up
        eng.io[unit] for a program that OPENs `name:` (e.g. a 'GAM:' device)."""
        self.device_handlers[name.upper()] = fn

    def mount_device(self, name, directory):
        """Mount logical device `name:` on host `directory`: a program that
        OPEN(DEVICE='name', FILE='F')s then reads/writes `directory`/F through the ordinary
        sequential file machinery -- the FILE= spec is just the filename within the mount. Lets
        a driver, or the CLI --mount option, attach a device (e.g. GAM: -> a terrain-map
        directory) without writing a bespoke handler. The filename is matched leniently (missing
        extension / case), the way _open_path resolves DSK files."""
        import os

        base = os.path.abspath(directory)

        def handler(eng, unit, specs, frame):
            fspec = eng._spec(specs.get("FILE") or specs.get("NAME") or "", frame)
            fname = eng.tgt.unpack(fspec).strip() if isinstance(fspec, int) else str(fspec).strip()
            path = os.path.join(base, fname)
            if not os.path.exists(path):  # lenient match, like _open_path (missing ext / case)
                low = os.path.basename(path).lower()
                try:
                    for f in os.listdir(base):
                        if f.lower() in (low, low + ".dat"):
                            path = os.path.join(base, f)
                            break
                except OSError:
                    pass
            access = specs.get("ACCESS")
            if access == "SEQOUT":
                eng.io[unit] = {
                    "recs": [],
                    "pos": 0,
                    "mode": "w",
                    "path": path,
                    "dec": eng.forots,
                }
            elif access == "SEQIN" or os.path.exists(path):
                eng.io[unit] = eng._open_read_unit(path)
            else:
                eng.io[unit] = {"recs": [], "pos": 0, "mode": "w", "path": path}

        self.register_device(name, handler)

    def _binio(self):
        """The unformatted-I/O codec (FOROTS record + DEC-10 float layout). It's a
        target-specific runtime, injected via forterp.runtime.install_runtime; the
        generic core has none, so binary I/O without it is a clear error."""
        if self.binio is None:
            raise RuntimeError(
                "unformatted/binary I/O needs a FORTRAN-10 runtime "
                "(forterp.runtime.install_runtime)"
            )
        return self.binio

    # ---- setup
    def _build(self):
        sizes = {}
        # first pass: size every common block to its largest layout. A member's
        # dimensions may come from a separate DIMENSION/type statement rather than
        # the COMMON statement itself (F66 6.2/7.2.1.1: declaration order is free),
        # so fall back to u.arrays when the COMMON entry carries no inline dims.
        for u in self.units.values():
            for block, members in u.commons:
                off = 0
                for name, dims in members:
                    d = dims or u.arrays.get(name)
                    off += array_size(d) if d else 1
                sizes[block] = max(sizes.get(block, 0), off)
        for block, n in sizes.items():
            self.commons[block] = self._alloc_words(n)

        for name, u in self.units.items():
            rt = UnitRT(u)
            for block, members in u.commons:
                off = 0
                for mname, dims in members:
                    d = dims or u.arrays.get(mname)
                    rt.common_map[mname] = (block, off, d)
                    off += array_size(d) if d else 1
            self._layout_equivalence(name, u, rt)  # EQUIVALENCE storage aliasing (V5 6.6)
            self.rts[name] = rt
        # ENTRY points (V5 15.7): map each entry name to (owning unit, pc, params)
        for uname, u in self.units.items():
            for i, stmt in enumerate(u.code):
                if isinstance(stmt, A.EntryStmt):
                    self.entries[stmt.name] = (uname, i, stmt.params)
        # initialize DATA / parameters into storage
        for name, u in self.units.items():
            self._apply_data(self.rts[name], u)

    def _layout_equivalence(self, uname, u, rt):
        """Allocate EQUIVALENCE groups (V5 6.6) into common_map: alias each member to
        a shared backing store -- a COMMON block if any member is in one (extending it
        FORWARD as needed; backward extension is clamped), else a synthetic per-unit
        block in self.commons. Offsets come from a weighted union-find that records
        each name's word offset relative to its component root. Reusing common_map
        means every read/write/array/DATA path resolves equivalenced names unchanged.

        NOTE: storage is one value-slot per element (not bit-level words), so a
        cross-type EQUIVALENCE shares the slot's value, not a reinterpreted bit
        pattern -- consistent with our REAL=double divergence."""
        if not u.equivs:
            return
        parent, off = {}, {}

        def find(x):
            if x not in parent:
                parent[x], off[x] = x, 0
                return x
            if parent[x] != x:
                p = parent[x]
                r = find(p)
                off[x] += off[p]
                parent[x] = r
            return parent[x]

        def union(a, b, delta):  # constrain base(b) = base(a) + delta
            ra, rb = find(a), find(b)
            if ra == rb:
                # already one component: the new constraint must agree, else the program
                # demands one name occupy two offsets -- a contradictory EQUIVALENCE (illegal
                # in F66; a conforming compiler diagnoses it rather than dropping one).
                if off[b] - off[a] != delta:
                    raise RuntimeError(
                        f"contradictory EQUIVALENCE: {b!r} is constrained to two storage offsets"
                    )
                return
            parent[rb] = ra
            off[rb] = off[a] + delta - off[b]

        def elem_off(name, subs):  # 0-based element offset within `name`
            if name not in u.arrays or not subs:
                return 0
            dims = u.arrays[name]
            vals = [self._const_eval_int(s, u) for s in subs]
            if len(vals) == 1:  # single subscript: array as 1-D
                return vals[0] - dims[0][0]
            return linidx(vals, dims)

        def size_of(name):
            return array_size(u.arrays[name]) if name in u.arrays else 1

        for group in u.equivs:
            if not group:
                continue
            n0, s0 = group[0]
            base0 = elem_off(n0, s0)
            find(n0)
            for ni, si in group[1:]:  # ni coincides with n0 at one word
                union(n0, ni, base0 - elem_off(ni, si))

        comps = {}
        for name in list(parent):
            comps.setdefault(find(name), []).append(name)

        eq_block = 0
        for root, members in comps.items():
            # A group may touch at most one COMMON block; equivalencing across two is illegal
            # (F66 10.2.1 -- each block's storage sequence is independent and can't be joined).
            blocks = {rt.common_map[m][0] for m in members if m in rt.common_map}
            if len(blocks) > 1:
                raise RuntimeError(
                    f"EQUIVALENCE associates two COMMON blocks {sorted(blocks)!r} (F66 10.2.1)"
                )
            anchor = next((m for m in members if m in rt.common_map), None)
            if anchor is not None:  # tie the whole group into a COMMON block
                block, coff, _ = rt.common_map[anchor]
                for m in members:
                    mo = coff + (off[m] - off[anchor])
                    if mo < 0:
                        # would prepend storage before the block's first element: F66 10.2.2
                        # forbids extending a COMMON block backward (V5 errors too). The old
                        # code silently clamped to 0, which mis-associated the member.
                        raise RuntimeError(
                            f"EQUIVALENCE extends COMMON {block!r} backward (F66 10.2.2): {m!r}"
                        )
                    rt.common_map[m] = (block, mo, u.arrays.get(m))
                    end = mo + size_of(m)
                    if end > self.max_array_words:
                        # a crafted EQUIVALENCE offset must not extend a COMMON block past the
                        # allocation cap any more than a huge DIMENSION can (see _alloc_words).
                        raise RuntimeError(
                            f"EQUIVALENCE extends COMMON {block!r} to {end} words, past the "
                            f"{self.max_array_words}-word limit"
                        )
                    if end > len(self.commons[block]):
                        self.commons[block].extend([0] * (end - len(self.commons[block])))
            else:  # purely local group -> synthetic block
                mn = min(off[m] for m in members)
                size = max(off[m] - mn + size_of(m) for m in members)
                key = f"$EQV.{uname}.{eq_block}"
                eq_block += 1
                self.commons[key] = self._alloc_words(size)
                for m in members:
                    rt.common_map[m] = (key, off[m] - mn, u.arrays.get(m))

    def type_of(self, unit, name):
        if name in unit.types:
            return unit.types[name]
        if name and name[0] in unit.implicit:
            return unit.implicit[name[0]]
        return "INTEGER" if (name and name[0] in DEFAULT_INT_LETTERS) else "REAL"

    def char_length(self, unit, name):
        """Declared length of a CHARACTER entity (default 1; 0 means assumed length `*(*)`)."""
        if name in unit.char_len:
            return unit.char_len[name]
        if name and name[0] in unit.implicit_char_len:  # IMPLICIT CHARACTER*len (letter)
            return unit.implicit_char_len[name[0]]
        return 1

    # ---- DATA initialization
    def _apply_data(self, rt, unit):
        for targets, values in unit.data:
            # Build the value stream LAZILY: a `DATA A/2000000000*1/` repeat count must not
            # materialize a 2-billion-element list (it would OOM before the cap on the target
            # array's own storage ever applied). _data_assign pulls only what the targets
            # consume, so chained itertools.repeat bounds memory to what is actually used.
            streams = []
            for count, v in values:
                if isinstance(v, A.StrLit) and self.character_type:
                    # CHARACTER DATA value: keep the raw str -- _data_assign fits it to each
                    # target (pad/truncate for a CHARACTER target, pack for a numeric Hollerith).
                    streams.append(itertools.repeat(v.value, count))
                    continue
                # a literal longer than one word (5 chars) spans consecutive
                # variables/elements: 'ABCDEFGHIJKL' -> 'ABCDE','FGHIJ','KL   '
                if isinstance(v, A.StrLit) and len(v.value) > self.tgt.chars_per_word:
                    cw = self.tgt.chars_per_word
                    words = tuple(
                        self.tgt.pack(v.value[i : i + cw]) for i in range(0, len(v.value), cw)
                    )
                    streams.append(itertools.chain.from_iterable(itertools.repeat(words, count)))
                else:
                    streams.append(itertools.repeat(self._const_val(v, unit), count))
            it = itertools.chain.from_iterable(streams)
            for tgt in targets:
                self._data_assign(rt, unit, tgt, it)

    def _const_value(self, v):
        """Materialize a stored PARAMETER value into a runtime value. A Hollerith
        constant is kept as a raw str by the parser (which has no Target) and packed
        here through the engine's target, so it matches a literal of the same text."""
        if isinstance(v, bool):  # .TRUE./.FALSE. PARAMETER; bool is an int subclass, test first
            return self.tgt.from_bool(v)
        return self.tgt.pack(v) if isinstance(v, str) else v

    def _const_val(self, v, unit):
        if isinstance(v, bool):  # .TRUE./.FALSE. in DATA; bool is an
            return self.tgt.from_bool(v)  # int subclass, so test it FIRST.
        if isinstance(v, A.StrLit):  # FORTRAN-10: .TRUE.=-1, .FALSE.=0
            return self.tgt.pack(v.value)
        if isinstance(v, A.Complex):  # complex constant in DATA
            return complex(float(self._const_val(v.re, unit)), float(self._const_val(v.im, unit)))
        if isinstance(v, A.Var):
            return self._const_value(unit.consts.get(v.name, 0))
        if isinstance(v, float):
            return v
        return self.tgt.wrap(v) if isinstance(v, int) else v

    def _fit_data_value(self, val, unit, name):
        """Fit a pulled DATA value to its target: a CHARACTER target takes a str padded/truncated
        to its declared length; a Hollerith str into a numeric slot is packed via the target."""
        if isinstance(val, str):
            if self.type_of(unit, name) == "CHARACTER":
                n = self.char_length(unit, name)
                return val[:n].ljust(n) if n else val
            return self.tgt.pack(val)
        return val

    def _data_assign(self, rt, unit, tgt, it):
        if isinstance(tgt, A.Var):
            if tgt.name in unit.arrays:
                view, dims = self._static_array(rt, unit, tgt.name)
                for i in range(array_size(dims)):
                    view.loc(i).write(self._fit_data_value(next(it), unit, tgt.name))
            else:
                self._scalar_static_ref(rt, unit, tgt.name).write(
                    self._fit_data_value(next(it), unit, tgt.name)
                )
        elif isinstance(tgt, A.Ref):
            view, dims = self._static_array(rt, unit, tgt.name)
            subs = [self._const_eval_int(a, unit) for a in tgt.args]
            view.loc(linidx(subs, dims)).write(self._fit_data_value(next(it), unit, tgt.name))
        elif isinstance(tgt, A.Substring):  # DATA CVN001(lo:hi) / value / -- splice into the base
            base = tgt.base
            n = self.char_length(unit, base.name)
            if isinstance(base, A.Ref):
                view, dims = self._static_array(rt, unit, base.name)
                subs = [self._const_eval_int(a, unit) for a in base.args]
                ref = view.loc(linidx(subs, dims))
            else:
                ref = self._scalar_static_ref(rt, unit, base.name)
            lo = self._const_eval_int(tgt.lo, unit) if tgt.lo is not None else 1
            hi = self._const_eval_int(tgt.hi, unit) if tgt.hi is not None else n
            cur = ref.read()
            cur = cur.ljust(n)[:n] if isinstance(cur, str) else " " * n
            width = max(hi - lo + 1, 0)
            rhs = str(next(it))[:width].ljust(width)
            ref.write((cur[: lo - 1] + rhs + cur[hi:])[:n].ljust(n))
        elif isinstance(tgt, A.ImpliedDo):
            lo = self._const_eval_int(tgt.start, unit)
            hi = self._const_eval_int(tgt.stop, unit)
            step = self._const_eval_int(tgt.step, unit) if tgt.step else 1
            i = lo
            while (step > 0 and i <= hi) or (step < 0 and i >= hi):
                unit.consts[tgt.var] = i  # transient loop var
                for sub in tgt.items:
                    self._data_assign(rt, unit, sub, it)
                i += step
            unit.consts.pop(tgt.var, None)

    def _const_eval_int(self, node, unit):
        if isinstance(node, A.IntLit):
            return node.value
        if isinstance(node, A.OctalLit):
            return node.value
        if isinstance(node, A.Var):
            return self._const_value(unit.consts[node.name])
        if isinstance(node, A.Unary):
            v = self._const_eval_int(node.operand, unit)
            return -v if node.op == "-" else v
        if isinstance(node, A.Binary):
            a = self._const_eval_int(node.left, unit)
            b = self._const_eval_int(node.right, unit)
            return {"+": a + b, "-": a - b, "*": a * b, "/": trunc_div(a, b)}[node.op]
        raise RuntimeError(f"bad DATA subscript {node}")

    def _alloc_words(self, n):
        """A flat word store of length n, capped at max_array_words so a hostile or accidental
        huge DIMENSION raises a clean error instead of OOM-ing the host."""
        if n > self.max_array_words:
            raise RuntimeError(
                f"array allocation of {n} words exceeds the {self.max_array_words}-word limit "
                "(set eng.max_array_words higher if this is intended)"
            )
        return [0] * n

    def _static_array(self, rt, unit, name):
        dims = unit.arrays[name]
        if name in rt.common_map:
            block, off, _ = rt.common_map[name]
            return ArrayView(self.commons[block], off), dims
        if name not in rt.local_arrays:
            rt.local_arrays[name] = self._alloc_words(array_size(dims))
        return ArrayView(rt.local_arrays[name], 0), dims

    def _array_base(self, frame, name):
        """The backing store and base offset of array `name`, without building an ArrayView
        -- the read/write fast paths use this with oob_read/oob_write. (arrayview() builds
        the ArrayView object, which is still what array-argument passing and I/O need.)"""
        a = frame.args.get(name)
        if a is not None:  # an array dummy: a CellRef actual seq-associates from its element
            return (a.store, a.idx) if type(a) is CellRef else (a.store, a.base)
        rt = frame.rt
        slot = rt.common_map.get(name)
        if slot is not None:
            return self.commons[slot[0]], slot[1]
        arr = rt.local_arrays.get(name)
        if arr is None:
            arr = rt.local_arrays[name] = self._alloc_words(array_size(rt.unit.arrays[name]))
        return arr, 0

    def _scalar_static_ref(self, rt, unit, name):
        if name in rt.common_map:
            block, off, _ = rt.common_map[name]
            return CellRef(self.commons[block], off)
        return DictRef(rt.local_scalars, name)

    # ---- name resolution within a running frame
    def arrayview(self, frame, name):
        rt, unit = frame.rt, frame.rt.unit
        if name in frame.args:
            a = frame.args[name]
            # An array element actual (X(I) -> CellRef) bound to an array dummy is
            # FORTRAN sequence association: the dummy's first element IS X(I), the next
            # is X(I+1), ... Re-view the cell's storage at its offset as the array base.
            if isinstance(a, CellRef):
                return ArrayView(a.store, a.idx)
            return a
        return self._static_array(rt, unit, name)[0]

    def _dims(self, name, frame):
        """Resolve an array's (lo,hi) bounds, evaluating any adjustable (dummy-arg)
        dimension expressions in the current frame. Fast-paths all-constant dims."""
        raw = frame.rt.unit.arrays[name]
        for lo, hi in raw:
            if type(lo) is not int or type(hi) is not int:
                return [
                    (
                        lo if type(lo) is int else int(self.eval(lo, frame)),
                        hi if type(hi) is int else int(self.eval(hi, frame)),
                    )
                    for lo, hi in raw
                ]
        return raw

    def scalar_ref(self, frame, name):
        rt, unit = frame.rt, frame.rt.unit
        if name in frame.args:
            return frame.args[name]
        return self._scalar_static_ref(rt, unit, name)

    # ---- expression evaluation
    def eval(self, node, frame):
        # Ordered hottest-first: at run time, variable reads, arithmetic, integer constants,
        # and array elements dominate; the rarer literal node types follow.
        t = type(node)
        if t is A.Var:
            return self.eval_var(node.name, frame)
        if t is A.Binary:
            return self.eval_binary(node, frame)
        if t is A.IntLit:
            return node.value
        if t is A.Ref:
            return self.eval_ref(node, frame)
        if t is A.RealLit:
            return node.value
        if t is A.Unary:
            v = self.eval(node.operand, frame)
            if node.op == "NOT":
                return self.tgt.lnot(v)  # PDP-10: bitwise complement (36-bit)
            if node.op == "-":
                return self.tgt.wrap(-v) if isinstance(v, int) else -v
            return v
        if t is A.OctalLit:
            return self.tgt.wrap(node.value)
        if t is A.StrLit:
            # F77: a string literal is a CHARACTER constant (a Python str). Otherwise it is a
            # Hollerith datum packed left-justified into a word (the F66 / FORTRAN-10 model).
            return node.value if self.character_type else self.tgt.pack(node.value)
        if t is A.LogicalLit:
            return self.tgt.from_bool(node.value)  # FORTRAN-10 .TRUE.=-1, .FALSE.=0
        if t is A.Complex:  # (re, im) complex constant
            return complex(float(self.eval(node.re, frame)), float(self.eval(node.im, frame)))
        if t is A.Substring:  # CHARACTER substring NAME(lo:hi) -- 1-based, inclusive
            s = str(self.eval(node.base, frame))
            lo = int(self.eval(node.lo, frame)) if node.lo is not None else 1
            hi = int(self.eval(node.hi, frame)) if node.hi is not None else len(s)
            return s[lo - 1 : hi]
        raise RuntimeError(f"cannot eval {node}")

    def _name_is_unbound(self, name, frame, unit, *, exclude_assigned=True):
        """True if `name` is not a local variable in this unit -- not a dummy argument, a
        COMMON member, or an explicitly typed name (and, unless `exclude_assigned` is False,
        not an ASSIGN target). Such a name can instead resolve to an ENTRY, an external
        function, or a builtin."""
        if name in frame.args or name in frame.rt.common_map or name in unit.types:
            return False
        return not (exclude_assigned and name in frame.rt.assigned)

    def eval_var(self, name, frame):
        unit = frame.rt.unit
        if name in unit.consts:
            return self._const_value(unit.consts[name])
        if name in unit.arrays:  # bare array name (I/O / arg use)
            return self.arrayview(frame, name)
        if name in self.entries and self._name_is_unbound(name, frame, unit):
            return self._call_entry_func(name, [], frame)  # no-arg ENTRY function ref
        if (
            name != frame.rt.unit.name
            and name in self.units
            and self.units[name].kind == "function"
            and self._name_is_unbound(name, frame, unit)
        ):
            return self.call_function(name, [], frame)
        # the builtin fallback historically does NOT exclude ASSIGN targets
        if name in self.builtins and self._name_is_unbound(
            name, frame, unit, exclude_assigned=False
        ):
            return self.builtins[name](self, frame, [])
        # plain scalar read: fetch the value directly, allocating no per-read reference
        # object (the hot path). scalar_ref() builds a CellRef/DictRef -- only writes and
        # argument passing need that.
        if name in frame.args:
            return frame.args[name].read()
        slot = frame.rt.common_map.get(name)
        if slot is not None:
            return self.commons[slot[0]][slot[1]]
        return frame.rt.local_scalars.get(name, 0)

    def eval_ref(self, node, frame):
        name = node.name
        unit = frame.rt.unit
        if name in unit.arrays:
            dims = self._dims(name, frame)
            subs = [self.eval(a, frame) for a in node.args]
            store, base = self._array_base(frame, name)  # read directly, no CellRef/ArrayView
            return oob_read(store, base + linidx(subs, dims))
        proc = frame.args.get(name)
        if isinstance(proc, ProcRef):  # reference to a dummy procedure (function)
            t = proc.target
            if t not in self.rts and (t in INTRINSICS or t in _CHAR_LOGICAL):
                # the actual was an intrinsic name (F77 15.10) -- dispatch to the library
                return self._apply_intrinsic(t, [self.eval(a, frame) for a in node.args])
            return self.call_function(t, node.args, frame)
        if name in unit.stmt_funcs:
            return self._call_stmt_func(name, node.args, frame)
        if name in self.entries:  # V5 15.7: function ENTRY reference
            return self._call_entry_func(name, node.args, frame)
        if name in unit.externals and name in self.units and self.units[name].kind == "function":
            return self.call_function(name, node.args, frame)  # V5 15.3: EXTERNAL beats intrinsic
        if (name in INTRINSICS or name in _CHAR_LOGICAL) and (
            self.dec_intrinsics or name in _F66_INTRINSICS
        ):
            return self._apply_intrinsic(name, [self.eval(a, frame) for a in node.args])
        if name in self.units and self.units[name].kind == "function":
            return self.call_function(name, node.args, frame)
        if name in self.builtins:
            return self.builtins[name](self, frame, node.args)
        raise RuntimeError(f"unknown function/array {name!r}")

    def _call_stmt_func(self, name, arg_nodes, frame):
        """Evaluate a FORTRAN-66 statement function: bind its dummy params to the
        actual values, evaluate its body expression, then restore the locals it
        shadowed (the dummies are local to the statement function)."""
        params, body = frame.rt.unit.stmt_funcs[name]
        if len(arg_nodes) != len(params):
            raise RuntimeError(
                f"statement function {name} expects {len(params)} argument(s), got {len(arg_nodes)}"
            )
        actuals = [self.eval(a, frame) for a in arg_nodes]
        store = frame.rt.local_scalars
        saved = {p: store[p] for p in params if p in store}
        present = {p for p in params if p in store}
        for p, v in zip(params, actuals):
            store[p] = v
        try:
            # A statement function's value is converted to the function's own (implicit
            # or declared) type before use -- e.g. an INTEGER-named SF truncates a real
            # body result (X3.9-1978 15.4.1 / 15.5.2). Without this, IFOS05=...+IABS(...)
            # leaks the float through and the caller's arithmetic is off.
            return self._coerce_result(self.eval(body, frame), self.type_of(frame.rt.unit, name))
        finally:
            for p in params:
                if p in present:
                    store[p] = saved[p]
                else:
                    store.pop(p, None)

    def _coerce_result(self, val, ttype):
        """Convert a value to a procedure result type (the numeric subset of do_assign's
        type-boundary conversion; logicals and strings pass through unchanged)."""
        if isinstance(val, (bool, str)):
            return val
        if ttype == "COMPLEX":
            return val if isinstance(val, complex) else complex(float(val), 0.0)
        if isinstance(val, complex):  # complex -> scalar uses the real part
            return self.tgt.wrap(int(val.real)) if ttype == "INTEGER" else val.real
        if ttype in ("REAL", "DOUBLE PRECISION") and isinstance(val, int):
            return float(val)
        if ttype == "INTEGER" and isinstance(val, float):
            return self.tgt.wrap(int(val))
        return val

    def _lib_warn(self, msg):
        """Emit a FOROTS LIB/APR warning (V5 App H) and count it. ERRSET caps how
        many are printed; beyond the cap they still occur but are not listed."""
        self.lib_apr_count += 1
        if self.lib_apr_count <= self.errset_limit:
            self.emit(msg + "\n")

    def _apply_intrinsic(self, name, args):
        """Apply a library intrinsic. FORTRAN-10 V5 (Appendix H, Table H-2): math
        LIB domain errors -- SQRT/LOG of a negative arg, ASIN/ACOS of |arg|>1 --
        and APR floating overflow are "reported as warnings and the program
        continues"; they must NOT raise. We print the manual's exact message and
        return a defined recovery value computed on the nearest in-domain argument
        (|x| for SQRT/LOG, clamp to [-1,1] for ASIN/ACOS). FORLIB's exact recovery
        value isn't specified in the V5 manual, so this is a documented
        approximation -- same class as REAL=Python double."""
        if name == "LSH":  # PDP-10 logical word shift: width from the target
            return _lsh(self.tgt, args[0], args[1])
        if name == "ROT":  # PDP-10 logical word rotate: width from the target
            return _rot(self.tgt, args[0], args[1])
        if name in _CHAR_LOGICAL:  # LGE/LGT/LLE/LLT: blank-padded lexical compare -> logical
            a, b = str(args[0]), str(args[1])
            w = max(len(a), len(b))
            return self.tgt.from_bool(_CHAR_LOGICAL[name](a.ljust(w), b.ljust(w)))
        if args and isinstance(args[0], complex) and name in _COMPLEX_GENERIC:
            name = _COMPLEX_GENERIC[name]  # F77 generic: a complex arg picks the C-variant
        try:
            r = INTRINSICS[name](args)
        except ValueError:  # math domain error (negative / out of range)
            if name not in _LIB_MSG:
                raise
            self._lib_warn(_LIB_MSG[name])
            r = _LIB_RECOVER[name](args)
        except OverflowError:  # APR floating overflow (e.g. EXP of large arg)
            self._lib_warn("Floating Overflow")
            return math.inf if (args and args[0] > 0) else -math.inf
        # INT-family conversions take the target's integer wrap (PDP-10: 36-bit 2's-comp)
        return self.tgt.wrap(int(r)) if name in _INT_RESULT else r

    def eval_binary(self, node, frame):
        op = node.op
        # Logical connectives go through the target: PDP-10 acts BITWISE on the full
        # 36-bit word (Ch 4, p4-7, operands -1/0); a portable target is boolean.
        if op == "AND":
            return self.tgt.land(self.eval(node.left, frame), self.eval(node.right, frame))
        if op == "OR":
            return self.tgt.lor(self.eval(node.left, frame), self.eval(node.right, frame))
        if op in ("XOR", "NEQV"):
            return self.tgt.lxor(self.eval(node.left, frame), self.eval(node.right, frame))
        if op == "EQV":
            return self.tgt.leqv(self.eval(node.left, frame), self.eval(node.right, frame))
        if self.character_type:  # F77 CHARACTER ops -- only the F77 dialect produces str operands
            if op == "CONCAT":  # concatenation
                return str(self.eval(node.left, frame)) + str(self.eval(node.right, frame))
        a = self.eval(node.left, frame)
        b = self.eval(node.right, frame)
        if self.character_type and (isinstance(a, str) or isinstance(b, str)):
            a, b = str(a), str(b)  # CHARACTER comparison: blank-pad to equal length, then
            w = max(len(a), len(b))  # compare on the ASCII collating sequence (X3.9-1978 6.3.5)
            a, b = a.ljust(w), b.ljust(w)
        fl = isinstance(a, float) or isinstance(b, float)
        cx = isinstance(a, complex) or isinstance(b, complex)
        # arithmetic first (the hot ops); an integer result takes the target's word wrap
        if op == "+":
            return a + b if (fl or cx) else self.tgt.wrap(a + b)
        if op == "-":
            return a - b if (fl or cx) else self.tgt.wrap(a - b)
        if op == "*":
            return a * b if (fl or cx) else self.tgt.wrap(a * b)
        if op == "/":
            if cx:
                return a / b if b != 0 else 0j  # complex divide (non-fatal /0)
            if fl:
                return a / b if b != 0 else 0.0  # FOROTS divide-by-zero: non-fatal
            return trunc_div(a, b)  # (handles b==0 -> 0)
        # relational results are FORTRAN logicals (target's convention: PDP-10 -1/0)
        if op == "EQ":
            return self.tgt.from_bool(a == b)
        if op == "NE":
            return self.tgt.from_bool(a != b)
        if op in ("LT", "LE", "GT", "GE") and cx:
            return self.tgt.from_bool(False)  # V5 CTR: complex .LT./.GT./... undefined
        if op == "LT":
            return self.tgt.from_bool(a < b)
        if op == "LE":
            return self.tgt.from_bool(a <= b)
        if op == "GT":
            return self.tgt.from_bool(a > b)
        if op == "GE":
            return self.tgt.from_bool(a >= b)
        if op == "^":
            if cx:
                return a**b  # complex exponentiation
            if fl:
                if a == 0 and b < 0:
                    return 0.0  # 0.0**negative: non-fatal stand-in
                if a < 0 and b != int(b):  # F66 6.4: neg base ** real exp = undefined
                    self._lib_warn("Negative Number to a Real Power")  # FOROTS LIB error
                    return abs(a) ** b  # real stand-in (Python would give complex)
                return a**b
            base, exp = int(a), int(b)
            if exp < 0:  # FORTRAN integer**negative truncates
                if base == 1:
                    return 1
                if base == -1:
                    return 1 if exp % 2 == 0 else -1
                return 0  # |base|>1 -> 0; base 0 -> 0 (no crash)
            return self.tgt.wrap(base**exp)
        raise RuntimeError(f"bad operator {op}")

    # ---- argument passing
    def arg_ref(self, node, frame):
        """Build a reference/view for an actual argument (pass by reference)."""
        if isinstance(node, A.Var):
            name = node.name
            unit = frame.rt.unit
            if name in unit.consts:
                return TempRef(self._const_value(unit.consts[name]))
            if name in unit.arrays:
                return self.arrayview(frame, name)
            # a procedure name passed as an argument (F66 8.3): EXTERNAL-declared,
            # or a dummy procedure being passed down another level
            if isinstance(frame.args.get(name), ProcRef):
                return frame.args[name]
            if name in unit.externals and (name in self.units or name in self.builtins):
                return ProcRef(name)
            # an intrinsic name (INTRINSIC-affirmed, F77 15.10) passed as an actual arg, but
            # not shadowed by a local variable -- pass the library function by reference
            if name in unit.intrinsics and name not in unit.types and name not in frame.args:
                return ProcRef(name)
            return self.scalar_ref(frame, name)
        if isinstance(node, A.Ref) and node.name in frame.rt.unit.arrays:
            dims = self._dims(node.name, frame)
            subs = [self.eval(a, frame) for a in node.args]
            return self.arrayview(frame, node.name).loc(linidx(subs, dims))
        if self.character_type and isinstance(node, A.Substring):
            # a CHARACTER substring lvalue (S(lo:hi)) used as an I/O item / actual argument:
            # a writable view that splices back into the base (not a read-only temporary)
            base = self.arg_ref(node.base, frame)
            n = self.char_length(frame.rt.unit, node.base.name)
            lo = int(self.eval(node.lo, frame)) if node.lo is not None else 1
            hi = int(self.eval(node.hi, frame)) if node.hi is not None else n
            return SubstringRef(base, lo, hi, n)
        return TempRef(self.eval(node, frame))

    def bind_args(self, callee_rt, actuals):
        params = callee_rt.unit.params
        return {p: actuals[i] for i, p in enumerate(params) if i < len(actuals)}

    # ---- calls
    def _entry_frame(self, name, arg_nodes, frame):
        """Build a frame entering `name`'s owning unit at the ENTRY's pc, bound to
        the ENTRY's own dummy args (V5 15.7). Returns (frame, owner_rt, alt_labels)."""
        owner, epc, eparams = self.entries[name]
        crt = self.rts[owner]
        actuals, alt_labels = [], []
        for a in arg_nodes:
            if isinstance(a, A.LabelArg):
                alt_labels.append(a.label)
                actuals.append(None)
            else:
                actuals.append(self.arg_ref(a, frame))
        binding = {
            p: actuals[i]
            for i, p in enumerate(eparams)
            if p != "*" and i < len(actuals) and actuals[i] is not None
        }
        f = Frame(crt, binding)
        f.pc = epc  # begin at the ENTRY (a no-op) -> next stmt
        return f, crt, alt_labels

    def _call_entry_func(self, name, arg_nodes, frame):
        f, crt, _ = self._entry_frame(name, arg_nodes, frame)
        self.run(f)
        return crt.local_scalars.get(name, 0)  # value returned via the entry name

    def call_sub(self, name, arg_nodes, frame):
        proc = frame.args.get(name)
        if isinstance(proc, ProcRef):  # CALL <dummy procedure>(...)
            return self.call_sub(proc.target, arg_nodes, frame)
        if name in self.builtins:
            self.builtins[name](self, frame, arg_nodes)
            return None
        if name in self.entries:  # CALL of an ENTRY point (V5 15.7)
            f, crt, alt_labels = self._entry_frame(name, arg_nodes, frame)
            alt = self.run(f)
            if alt and 1 <= alt <= len(alt_labels):
                return Goto(alt_labels[alt - 1])
            return None
        callee = self.units.get(name)
        if callee is None:
            raise RuntimeError(f"undefined subroutine {name!r}")
        crt = self.rts[name]
        params = crt.unit.params
        # split actuals into value refs and alternate-return labels (the latter
        # align positionally with '*' dummy params)
        actuals, alt_labels = [], []
        for a in arg_nodes:
            if isinstance(a, A.LabelArg):
                alt_labels.append(a.label)
                actuals.append(None)
            else:
                actuals.append(self.arg_ref(a, frame))
        binding = {
            p: actuals[i]
            for i, p in enumerate(params)
            if p != "*" and i < len(actuals) and actuals[i] is not None
        }
        alt = self.run(Frame(crt, binding))  # RETURN e -> e, else None
        if alt and 1 <= alt <= len(alt_labels):
            return Goto(alt_labels[alt - 1])  # jump in the CALLER
        return None

    def call_function(self, name, arg_nodes, frame):
        actuals = [self.arg_ref(a, frame) for a in arg_nodes]
        crt = self.rts[name]
        f = Frame(crt, self.bind_args(crt, actuals))
        self.run(f)
        return crt.local_scalars.get(name, 0)

    # ---- statement execution; returns None | Goto | Ret | Stop
    def exec_stmt(self, s, frame):
        t = type(s)
        if t is A.Assign:
            self.do_assign(s, frame)
            return None
        if t is A.Continue:
            return None
        if t is A.EntryStmt:  # V5 15.7: nonexecutable -> no-op
            return None
        if t is A.Goto:
            return Goto(s.target)
        if t is A.AssignLabel:  # ASSIGN <label> TO <var>
            self.scalar_ref(frame, s.var).write(self.tgt.wrap(s.tgt))
            return None
        if t is A.AssignedGoto:  # GO TO <var>  -> jump to stored label
            return Goto(int(self.eval_var(s.var, frame)))
        if t is A.CompGoto:
            i = self.eval(s.index, frame)
            if 1 <= i <= len(s.labels):
                return Goto(s.labels[i - 1])
            return None
        if t is A.IfLogical:
            if self.tgt.truthy(self.eval(s.cond, frame)):
                return self.exec_stmt(s.stmt, frame)
            return None
        if t is A.IfBranch:
            v = self.eval(s.cond, frame)
            if len(s.labels) == 3:
                k = 0 if (v < 0) else (1 if v == 0 else 2)
                return Goto(s.labels[k])
            return Goto(s.labels[0] if self.tgt.truthy(v) else s.labels[1])
        if t is A.Do:
            return self.exec_do(s, frame)
        if t is A.Call:
            return self.call_sub(s.name, s.args, frame)
        if t is A.Return:
            return Ret(self.eval(s.expr, frame) if s.expr is not None else None)
        if t is A.StopStmt:
            if s.code is not None:  # V5 9.6: STOP 'msg' / STOP n prints, then halts
                self.emit((s.code if isinstance(s.code, str) else str(s.code)) + "\n")
            return Stop()
        if t is A.PauseStmt:
            msg = "PAUSE" + (f" {s.code}" if s.code is not None else "")
            self.emit(msg + "\n")  # F66 PAUSE: print and continue (batch mode)
            return None
        if t is A.TypeStmt:
            self.do_type(s, frame)
            return None
        if t is A.AcceptStmt:
            return self._io_guard(s, self.do_accept, frame)
        if t in (A.IoStmt, A.FileCtl):
            return self._io_guard(s, self.do_io, frame)
        if t is A.DefineFile:
            return self.do_define_file(s, frame)
        if t is A.EncDec:
            return self._io_guard(s, self.do_encdec, frame)
        raise RuntimeError(f"cannot exec {s}")

    def _io_guard(self, s, do_fn, frame):
        """Run an I/O statement, routing a numeric input-conversion error (V5) to the
        READ's ERR= label if it has one, else letting it halt the program. Returns the
        statement's own control signal (e.g. a Goto from END=) when no error occurs."""
        from forterp.fmt import InputConversionError

        try:
            return do_fn(s, frame)
        except InputConversionError:
            self.last_io_error = IO_ILLEGAL_CHAR
            specs = getattr(s, "specs", None)
            err = specs.get("ERR") if specs else None
            if err is not None:
                return Goto(err)
            raise

    def _assign_substring(self, s, frame):
        """Assign to a CHARACTER substring target ``S(lo:hi) = expr``: splice the RHS (fitted to
        the substring width -- truncate / blank-pad) into the base's stored value, preserving its
        declared length (X3.9-1978 14.4). The rest of the base string is left unchanged."""
        sub = s.target
        ref = self.arg_ref(sub.base, frame)
        n = self.char_length(frame.rt.unit, sub.base.name)
        cur = ref.read()
        cur = cur.ljust(n)[:n] if isinstance(cur, str) else " " * n
        lo = int(self.eval(sub.lo, frame)) if sub.lo is not None else 1
        hi = int(self.eval(sub.hi, frame)) if sub.hi is not None else n
        width = max(hi - lo + 1, 0)
        rhs = str(self.eval(s.expr, frame))[:width].ljust(width)
        ref.write((cur[: lo - 1] + rhs + cur[hi:])[:n].ljust(n))

    def do_assign(self, s, frame):
        # The CHARACTER target forms (substring lvalue, fit-to-length scalar) exist only under
        # the F77 character_type dialect; gate them so F66/FORTRAN-10 skip the per-assign checks.
        if self.character_type and isinstance(s.target, A.Substring):
            return self._assign_substring(s, frame)
        val = self.eval(s.expr, frame)
        tgt = s.target
        # numeric conversion at the type boundary -- but a Hollerith/char constant
        # adopts the target type as a bit pattern (no conversion), e.g. TTY='TTY'
        ttype = self.type_of(frame.rt.unit, tgt.name)
        if self.character_type and ttype == "CHARACTER":
            # F77 character assignment: the value is a Python str; fit it to the target's
            # declared length -- truncate if longer, blank-pad if shorter (V5 / X3.9-1978 14.4).
            n = self.char_length(frame.rt.unit, tgt.name)
            val = str(val)
            val = (val[:n] if len(val) > n else val.ljust(n)) if n else val  # n=0: assumed length
        elif isinstance(val, bool) or isinstance(s.expr, A.StrLit):
            pass
        elif ttype == "COMPLEX":  # real/int -> complex(x, 0)
            if not isinstance(val, complex):
                val = complex(float(val), 0.0)
        elif isinstance(val, complex):  # complex -> scalar uses the real part
            val = self.tgt.wrap(int(val.real)) if ttype == "INTEGER" else val.real
        elif ttype in ("REAL", "DOUBLE PRECISION") and isinstance(val, int):
            val = float(val)
        elif ttype == "INTEGER" and isinstance(val, float):
            val = self.tgt.wrap(int(val))
        if isinstance(tgt, A.Var):
            # write directly, allocating no reference object (mirror of eval_var's read)
            name = tgt.name
            if name in frame.args:
                frame.args[name].write(val)
            else:
                slot = frame.rt.common_map.get(name)
                if slot is not None:
                    self.commons[slot[0]][slot[1]] = val  # in-range COMMON scalar slot
                else:
                    frame.rt.local_scalars[name] = val
        else:
            dims = self._dims(tgt.name, frame)
            subs = [self.eval(a, frame) for a in tgt.args]
            store, base = self._array_base(frame, tgt.name)
            oob_write(store, base + linidx(subs, dims), val)

    def exec_do(self, s, frame):
        start = self.eval(s.start, frame)
        stop = self.eval(s.stop, frame)
        step = self.eval(s.step, frame) if s.step else 1
        # X3.9-1978 11.10.2: the initial/terminal/increment parameters are converted to the
        # type of the DO variable BEFORE the iteration count is formed -- so an integer DO
        # variable with real bounds (DO I = 6.7, 9.325) truncates to 6,9,1 -> 4 trips, not the
        # 3 a raw-real (9.325-6.7+1) count would give.
        vtype = self.type_of(frame.rt.unit, s.var)
        if vtype == "INTEGER":
            start, stop, step = self.tgt.wrap(int(start)), int(stop), self.tgt.wrap(int(step))
        elif vtype in ("REAL", "DOUBLE PRECISION"):
            start, stop, step = float(start), float(stop), float(step)
        ref = self.scalar_ref(frame, s.var)
        ref.write(start)
        if isinstance(start, float) or isinstance(stop, float) or isinstance(step, float):
            trips = int((stop - start + step) / step)
        else:
            trips = trunc_div(stop - start + step, step)
        if s.term_label not in frame.rt.unit.labels:
            raise RuntimeError(f"DO loop terminal label {s.term_label} not found")
        term_idx = frame.rt.unit.labels[s.term_label]
        if trips < 1:
            if self.zero_trip_do:
                # F77 (X3.9-1978 11.10): a zero-trip loop skips the body entirely; the DO
                # variable keeps its initial value (already written above). The terminal
                # statement belongs to THIS loop and must not execute. But if an enclosing,
                # still-active DO shares this terminal label (a shared-terminal nest), that
                # outer loop's incrementation still has to run -- so drive its bookkeeping
                # directly here without executing the terminal statement.
                if any(d.term_idx == term_idx for d in frame.do_stack):
                    if self._do_bookkeep(frame, s.term_label):
                        frame.pc -= 1  # bookkeep set pc to the outer body; run loop adds 1 back
                    else:
                        frame.pc = term_idx  # every sharing loop done -> resume after terminal
                    return None
                frame.pc = term_idx
                return None
            trips = 1  # F66 / DEC FORTRAN-10 one-trip: the body always runs at least once
        # Starting this loop fresh invalidates any earlier instance left suspended by a
        # jump-out (extended range), so it can't later reactivate by mistake.
        if frame.do_suspended:
            frame.do_suspended = [d for d in frame.do_suspended if d.term_idx != term_idx]
        frame.do_stack.append(DoFrame(ref, trips, step, s.term_label, frame.pc + 1, term_idx))
        return None

    # ---- the per-unit run loop
    def run_program(self, program=None):
        """Run the main program and return self. `program` names the unit to run; with none,
        the first PROGRAM unit is chosen. Raises ValueError -- listing the available programs
        -- when there is nothing to run, so callers get a clear error, not a KeyError."""
        name = program or next((n for n, u in self.units.items() if u.kind == "program"), None)
        if name is None or name not in self.rts:
            progs = sorted(n for n, u in self.units.items() if u.kind == "program")
            available = ", ".join(progs) or "(none)"
            if program:
                raise ValueError(f"no unit named {program!r} to run (programs: {available})")
            raise ValueError(f"no PROGRAM unit to run (programs: {available})")
        try:
            self.run(Frame(self.rts[name], {}))
        except StopExecution:
            pass
        return self

    def run(self, frame):
        """Run `frame`'s unit to completion. A single loop serves both the normal and the
        debugged/profiled case. `tracer` is None by default and hoisted to a local, so on
        the fast path the per-statement hook is one predicted branch; when a tracer is
        installed we also maintain the active-frame stack (self.frames, for backtrace /
        step-over depth) and call it before each statement. `tracer`/`frames` are CLASS
        defaults -- never set in __init__ -- so a normal engine's instance __dict__, and
        thus its hot-loop attribute-access speed, is identical to the pre-debug engine
        (measured: adding them as instance attrs cost ~8% on a tight loop)."""
        tracer = self.tracer
        if tracer is not None:
            if type(self.frames) is tuple:  # first traced run -> a real per-instance stack
                self.frames = []
            self.frames.append(frame)
        try:
            code = frame.rt.unit.code
            labels = frame.rt.unit.labels
            do_terms = frame.rt.do_terms
            n = len(code)
            while 0 <= frame.pc < n:
                self.steps += 1
                if self.steps > self.max_steps:
                    self._budget_error(frame)
                s = code[frame.pc]
                if tracer is not None:  # debug/profile hook; pauses BEFORE the statement runs
                    tracer(s, frame)
                ctrl = self.exec_stmt(s, frame)
                if ctrl is None:
                    if (
                        s.label is not None
                        and s.label in do_terms
                        and self._do_bookkeep(frame, s.label)
                    ):
                        continue
                    frame.pc += 1
                elif type(ctrl) is Goto:
                    self._apply_goto(frame, ctrl.label, labels)
                elif type(ctrl) is Ret:
                    return ctrl.alt
                elif type(ctrl) is Stop:
                    raise StopExecution()
        finally:
            if tracer is not None:
                self.frames.pop()

    def backtrace(self):
        """The active call chain as [(unit_name, current_line), ...], outermost first
        (populated only during a traced / debugged run)."""
        out = []
        for f in self.frames:
            code = f.rt.unit.code
            line = code[f.pc].line if 0 <= f.pc < len(code) else None
            out.append((f.rt.unit.name, line))
        return out

    def _budget_error(self, frame):
        code, u = frame.rt.unit.code, frame.rt.unit
        raise RuntimeError(
            f"step budget exceeded in {u.name} pc={frame.pc} "
            f"line={code[frame.pc].line}: "
            f"{type(code[frame.pc]).__name__} | "
            f"do_stack={[(d.term, d.trips) for d in frame.do_stack]}"
        )

    def _apply_goto(self, frame, tgt, labels):
        """Resolve a GO TO target and adjust the DO stack for F66 7.1.2.8.2 extended
        range: suspend (don't discard) loops we leave, and resume any whose range we
        re-enter. Rare at run time -- not on the per-statement path -- so both run loops
        share it."""
        label = tgt[1] if isinstance(tgt, tuple) else tgt
        if label not in labels:
            raise RuntimeError(f"jump to undefined statement label {label}")
        newpc = labels[label] + (1 if isinstance(tgt, tuple) else 0)  # tuple = skip past term
        while frame.do_stack and not (
            frame.do_stack[-1].body <= newpc <= frame.do_stack[-1].term_idx
        ):
            frame.do_suspended.append(frame.do_stack.pop())
        reentered = [d for d in frame.do_suspended if d.body <= newpc <= d.term_idx]
        if reentered:
            frame.do_suspended = [
                d for d in frame.do_suspended if not (d.body <= newpc <= d.term_idx)
            ]
            reentered.sort(key=lambda d: d.body)
            frame.do_stack.extend(reentered)
        frame.pc = newpc

    def run_block(self, base_rt, code, labels, formats=None):
        """Run an arbitrary statement list (with its own `labels`) against the storage
        and declarations of an existing UnitRT, without disturbing that unit. The block
        executes through a transient unit that shares `base_rt`'s declarations and live
        store by reference, so it reads/writes the same variables/arrays/COMMON and
        resolves CALLs against the engine's units. This is the primitive the REPL uses
        to run a typed statement or DO block against the live session. A STOP ends the
        block, not the engine."""
        base = base_rt.unit
        blk = A.ProgramUnit(kind=base.kind, name=base.name)
        blk.types = base.types  # share declarations so names resolve as they do in `base`
        blk.arrays = base.arrays
        blk.implicit = base.implicit
        blk.consts = base.consts
        blk.stmt_funcs = base.stmt_funcs
        blk.externals = base.externals
        blk.formats = {**base.formats, **(formats or {})}
        blk.code = code
        blk.labels = labels
        rt = UnitRT(blk)  # derives do_terms / assigned-names from the block's own code
        rt.common_map = base_rt.common_map  # share the live store
        rt.local_scalars = base_rt.local_scalars
        rt.local_arrays = base_rt.local_arrays
        try:
            self.run(Frame(rt, {}))
        except StopExecution:
            pass

    def _do_bookkeep(self, frame, label):
        while frame.do_stack and frame.do_stack[-1].term == label:
            f = frame.do_stack[-1]
            f.trips -= 1
            if f.trips > 0:
                v = f.ref.read()
                f.ref.write(v + f.step if isinstance(v, float) else self.tgt.wrap(v + f.step))
                frame.pc = f.body
                return True
            # Loop done. F77 (X3.9-1978 11.10) leaves the index at the value that exceeded the
            # limit (start + count*step -> 11 after DO I=1,10); F66 / DEC FORTRAN-10 leave it at
            # the LAST value executed (10), so a post-loop `IF (I .EQ. n)` sentinel works.
            if self.zero_trip_do:
                v = f.ref.read()
                f.ref.write(v + f.step if isinstance(v, float) else self.tgt.wrap(v + f.step))
            frame.do_stack.pop()
        return False

    # ---- formatted terminal + file I/O
    @staticmethod
    def _ld_out(values):
        """List-directed output: each value, space-separated, default-formatted."""
        parts = []
        for v in values:
            if isinstance(v, complex):
                parts.append(f" ({v.real},{v.imag})")  # complex -> (re,im)
            else:
                parts.append(" " + (repr(v) if isinstance(v, float) else str(int(v))))
        return "".join(parts)

    @staticmethod
    def _cx_expand(values):
        """A COMPLEX value transfers as two reals under format control (V5 Ch4)."""
        out = []
        for v in values:
            if isinstance(v, complex):
                out.append(v.real)
                out.append(v.imag)
            else:
                out.append(v)
        return out

    def _ld_in(self, line, refs):
        """List-directed input: values separated by blanks/commas, converted by token form.
        Honors the repeat and terminator grammar: `r*c` gives the value c r times, `r*`
        skips r items (they keep their values), and `/` ends the read (the remaining items
        keep their values). A non-numeric field is a conversion error (routes to ERR=)."""
        import re

        from forterp.fmt import InputConversionError

        def value(tok):
            try:
                return int(tok)
            except ValueError:
                try:
                    return float(tok)
                except ValueError:
                    raise InputConversionError(
                        f"illegal character in list-directed field {tok!r}"
                    ) from None

        items = iter(refs)
        for tok in (t for t in re.split(r"[ ,\t]+", line.strip()) if t):
            if tok == "/":  # slash terminator: stop; remaining items keep their values
                return
            count, star, rest = tok.partition("*")
            if star and count.isdigit():  # r*c (repeat the value) or r* (skip r items)
                v = value(rest) if rest else None
                for _ in range(int(count)):
                    ref = next(items, None)
                    if ref is None:
                        return
                    if v is not None:  # r* leaves the skipped items untouched
                        ref.write(v)
                continue
            ref = next(items, None)
            if ref is None:
                return
            ref.write(value(tok))

    def do_type(self, s, frame):
        from forterp.fmt import apply_carriage, apply_carriage_advance, render

        self._forots_pending = False  # default; the forots formatted branch refines it below
        nml = self._nml_name(s.fmt, frame)
        if nml is not None:  # TYPE/PRINT of a NAMELIST group
            self.emit(self._nml_write(nml, frame))
            return
        values = self._unf_values(s.items, frame)
        if s.fmt == "*":  # list-directed output
            self.emit(self._ld_out(values) + "\n")
            return
        spec = self._fmt_spec(s.fmt, frame)
        items = self._parsed(spec)
        text, suppress = render(items, self._cx_expand(values), self.tgt)  # complex -> 2 reals
        if self.forots:
            self.emit(apply_carriage_advance(text))  # advance-before: no trailing newline
            # advance-before-print leaves no trailing newline, so a following terminal READ must
            # advance to finish the line -- unless the record suppressed it ($). FOROTS does this.
            self._forots_pending = not suppress
        else:
            text = apply_carriage(text)
            if not suppress:
                text += "\n"
            self.emit(text)

    def _term_read_advance(self):
        """FOROTS advances to a new line before a terminal read when the previous formatted
        terminal output (TYPE) left a pending advance: under advance-before-print a non-`$` record
        has no trailing newline, so the read completes the line. No-op unless eng.forots."""
        if self.forots and self._forots_pending:
            self.emit("\n")
        self._forots_pending = False

    def do_accept(self, s, frame):
        if getattr(s, "reread", False):
            line = getattr(self, "_last_input", "")  # REREAD: the last record again
            eof = False
        else:
            self._term_read_advance()  # FOROTS completes the pending output line before reading
            raw = self.readline()
            line = raw.rstrip("\r\n")  # the line terminator isn't record data
            self._last_input = line
            eof = raw == ""  # readline() returns "" only at end-of-input
        if eof or "\x1a" in line:  # CONTROL-Z = end-of-file (V5 terminal input)
            self.last_io_error = IO_EOF
            raise StopExecution()  # EOF on ACCEPT (no END=) ends the program
        self._apply_read_line(s, frame, line)

    def _apply_read_line(self, s, frame, line):
        """Distribute one input record to the io-list: a NAMELIST group, list-directed
        input (`*`), or under a FORMAT. Shared by ACCEPT / terminal READ and by an
        unopened unit-READ that auto-connects to the terminal (V5 unit 5)."""
        from forterp.fmt import read_values

        nml = self._nml_name(s.fmt, frame)
        if nml is not None:  # NAMELIST group
            self._nml_read(nml, line, frame)
            return
        if s.fmt == "*":  # list-directed input
            self._ld_in(line, self._unf_refs(s.items, frame))
            return
        spec = self._fmt_spec(s.fmt, frame)
        items = self._parsed(spec)
        reads = read_values(items, line, self.tgt, self.free_form_input, self.character_type)
        self._assign_reads(s.items, reads, frame)  # COMPLEX consumes 2 real fields

    def do_encdec(self, s, frame):
        """ENCODE/DECODE (V5 10.15): internal formatted I/O to a packed-ASCII buffer.
        ENCODE renders the list per the FORMAT into the buffer; DECODE parses the
        buffer per the FORMAT into the list. No carriage control (it's not a record
        to a device) -- render() output goes straight to the buffer."""
        from forterp.fmt import read_values, render

        count = int(self.eval(s.count, frame))
        spec = self._fmt_spec(s.fmt, frame)
        items = self._parsed(spec)
        buf = self.arg_ref(s.buf, frame)
        cw = self.tgt.chars_per_word
        if s.decode:
            nwords = (count + cw - 1) // cw
            chunks = [
                self.tgt.unpack(
                    buf.loc(i).read() if hasattr(buf, "loc") else (buf.read() if i == 0 else 0), cw
                )
                for i in range(nwords)
            ]
            text = "".join(chunks)[:count]
            refs = self._unf_refs(s.items, frame)
            if s.fmt == "*":
                self._ld_in(text, refs)
            else:
                for ref, (_, v) in zip(
                    refs, read_values(items, text, self.tgt, self.free_form_input)
                ):
                    ref.write(v)
        else:
            values = self._unf_values(s.items, frame)
            text = self._ld_out(values) if s.fmt == "*" else render(items, values, self.tgt)[0]
            text = text[:count].ljust(count)  # fill the buffer to `count`
            words = [self.tgt.pack(text[i : i + cw].ljust(cw)) for i in range(0, count, cw)]
            if hasattr(buf, "loc"):
                for i, w in enumerate(words):
                    buf.loc(i).write(w)
            elif words:
                buf.write(words[0])  # scalar buffer: first word only

    # ---- NAMELIST-controlled I/O (V5 Ch11) ---------------------------------
    def _nml_name(self, fmt, frame):
        """If `fmt` names a NAMELIST group in this unit, return that name, else None."""
        nm = fmt.name if isinstance(fmt, A.Var) else fmt
        return nm if (isinstance(nm, str) and nm in frame.rt.unit.namelists) else None

    def _fmt_spec(self, fmt, frame):
        """Resolve a FORMAT reference to its spec text. An integer is a statement label
        -> the FORMAT statement's text. A variable or array name is a RUN-TIME format
        (F66 7.2.3.10): the Hollerith characters it holds, read from its first element
        until the format's parentheses balance. '*' or None -> None (list-directed /
        unformatted)."""
        if fmt is None or fmt == "*":
            return None
        if isinstance(fmt, int):
            spec = frame.rt.unit.formats.get(fmt)
            if spec is None:
                raise RuntimeError(f"FORMAT statement label {fmt} not found")
            return spec
        # a Hollerith array/variable holding the format text, referenced by name
        out, depth, started = [], 0, False
        for ref in self._item_refs(fmt, frame):
            for c in self.tgt.unpack(ref.read()):
                if not started:
                    if c == "(":
                        started = True
                        depth = 1
                        out.append(c)
                    continue
                out.append(c)
                depth += 1 if c == "(" else (-1 if c == ")" else 0)
            if started and depth <= 0:
                break
        return "".join(out) if started else None

    def _parsed(self, spec):
        """A parsed FORMAT for `spec`, memoized by its text (see self._fmt_cache).
        Falsy spec (list-directed / unformatted) -> empty item list."""
        if not spec:
            return []
        fmt = self._fmt_cache.get(spec)
        if fmt is None:
            from forterp.fmt import parse_format

            fmt = parse_format(spec)
            self._fmt_cache[spec] = fmt
        return fmt

    def _nml_write(self, gname, frame):
        """Build a re-readable NAMELIST output record: ` $NAME V= vals, ... $END`.
        (Field widths are list-directed-style, not the manual's column layout --
        a documented approximation; the structure round-trips through _nml_read.)"""
        out = [f" ${gname}\n"]
        for it in frame.rt.unit.namelists[gname]:
            vname = it.name if isinstance(it, (A.Var, A.Ref)) else str(it)
            vals = self._unf_values([it], frame)
            body = ", ".join(repr(v) if isinstance(v, float) else str(int(v)) for v in vals)
            out.append(f" {vname}= {body},\n")
        out.append(" $END\n")
        return "".join(out)

    def _nml_read(self, gname, line, frame):
        """Parse a NAMELIST input record ($NAME V=vals,... $) and assign (V5 11.2.1)."""
        import re

        refmap = {
            (it.name if isinstance(it, (A.Var, A.Ref)) else str(it)): self._item_refs(it, frame)
            for it in frame.rt.unit.namelists[gname]
        }
        body = line
        m = re.search(r"[$&]\s*[A-Za-z][A-Za-z0-9]*", body)  # skip past the $NAME
        if m:
            body = body[m.end() :]
        e = re.search(r"[$&]", body)  # stop at the closing $
        if e:
            body = body[: e.start()]
        parts = re.split(r"([A-Za-z][A-Za-z0-9]*(?:\s*\([^)]*\))?)\s*=", body)
        i = 1
        while i + 1 < len(parts):
            target = parts[i].strip()
            base = target.split("(")[0].strip().upper()[:6]
            refs = refmap.get(base)
            if refs:
                off = 0
                if "(" in target:  # A(2,3)= -> start at that element
                    sub = target[target.index("(") + 1 : target.rindex(")")]
                    off = self._nml_offset(base, sub, frame)
                self._nml_store(parts[i + 1], refs[off:])
            i += 2

    def _nml_offset(self, base, substr, frame):
        """0-based linear element offset for a subscripted NAMELIST input target."""
        dims = frame.rt.unit.arrays.get(base)
        if not dims:
            return 0
        try:
            subs = [int(x) for x in substr.split(",")]
        except ValueError:
            return 0
        return linidx(subs, dims)

    def _nml_store(self, valstr, refs):
        vals = []
        for tok in valstr.split(","):
            tok = tok.strip()
            if not tok:
                continue
            if "*" in tok:  # V5: repetition factor  n*k
                n, _, k = tok.partition("*")
                try:
                    vals.extend([self._nml_const(k)] * int(n))
                except ValueError:
                    vals.append(self._nml_const(tok))
            else:
                vals.append(self._nml_const(tok))
        for ref, v in zip(refs, vals):
            ref.write(v)

    def _nml_const(self, tok):
        t = tok.strip().upper()
        if t in ("T", ".TRUE."):
            return self.tgt.from_bool(True)  # logical .TRUE.
        if t in ("F", ".FALSE."):
            return self.tgt.from_bool(False)
        try:
            return self.tgt.wrap(int(t))
        except ValueError:
            try:
                return float(t)
            except ValueError:
                # Not a logical/int/real: a conversion error, like formatted input, rather
                # than a silent pack of the characters. (Round-trips are numeric, so this
                # only fires on genuinely bad input.) Routes via _io_guard to ERR=.
                from forterp.fmt import InputConversionError

                raise InputConversionError(
                    f"illegal character in NAMELIST field {tok.strip()!r}"
                ) from None

    def _formatted_write(self, s, frame, sink=None):
        """Formatted WRITE(unit,fmt) to a character device. `sink` is where the
        rendered text goes -- the terminal (default) or the line printer."""
        from forterp.fmt import apply_carriage, render

        sink = sink or self.emit
        values = self._unf_values(s.items, frame)
        if s.fmt == "*":  # list-directed output
            sink(self._ld_out(values) + "\n")
            return
        spec = self._fmt_spec(s.fmt, frame)
        items = self._parsed(spec)
        text, suppress = render(items, self._cx_expand(values), self.tgt)  # complex -> 2 reals
        # advance-before only for terminal output (sink is emit); printer/file keep newline-after
        if self.forots and sink is self.emit:
            from forterp.fmt import apply_carriage_advance

            sink(apply_carriage_advance(text))
            return
        text = apply_carriage(text)
        if not suppress:
            text += "\n"
        sink(text)

    def do_define_file(self, s, frame):
        """DEFINE FILE u(m,n,U,v) (V5 10.3.5): set up random-access units. We model the
        record store in memory; the associated variable `v` tracks the next record."""
        for d in s.defs:
            unit = int(self.eval(d["unit"], frame))
            st = self.io.setdefault(unit, {"recs": [], "pos": 0, "mode": "random"})
            st["mode"] = "random"
            st["assoc"] = d["assoc"]
            st["pos"] = st.get("pos", 0)
            self._set_assoc(st, frame, 1)  # associated var starts at record 1
        return None

    def _set_assoc(self, st, frame, nextrec):
        """Update a random unit's associated variable with the next record number."""
        st["nextrec"] = int(nextrec)  # also tracked on the unit for INQUIRE(NEXTREC=)
        name = st.get("assoc")
        if name:
            self.scalar_ref(frame, name).write(self.tgt.wrap(int(nextrec)))

    def _fmt_items(self, s, frame):
        """Parsed FORMAT items if this random I/O is formatted (a label), else None
        (unformatted or list-directed -> raw value-list record)."""

        if s.fmt is None or s.fmt == "*":
            return None
        spec = self._fmt_spec(s.fmt, frame)
        return self._parsed(spec) or None

    def _random_io(self, s, frame, unit):
        """Random-access READ/WRITE(u#r) and FIND(u#r) (V5 10.3.5/10.14): index the
        unit's records by number. A record holds either a raw value list (unformatted)
        or a rendered text line (formatted, when the statement carries a FORMAT). The
        associated variable (DEFINE FILE / OPEN) is updated to the next record number.
        Auto-opens an in-memory unit."""
        from forterp.fmt import read_values, render

        st = self.io.get(unit)
        if st is None:
            st = self.io[unit] = {"recs": [], "pos": 0, "mode": "random"}
        recs = st.setdefault("recs", [])
        rec = int(self._spec(s.specs.get("REC", 1), frame))  # 1-based record number
        items = self._fmt_items(s, frame)  # None => unformatted
        binmode = st.get("binary")  # OPEN MODE='BINARY'
        if s.mode == "FIND":
            st["pos"] = max(0, rec - 1)
            self._set_assoc(st, frame, rec)
            return None
        if s.mode == "WRITE":
            if rec < 1:  # invalid record number: an I/O error, not a negative-index clobber
                self.last_io_error = IO_BAD_RECORD
                return Goto(s.specs["ERR"]) if "ERR" in s.specs else None
            if binmode:  # FOROTS LSCW word record
                cells = [self._binio().encode_record(self._bin_words(s.items, frame))]
            elif items is not None:  # formatted: a '/' or FORMAT reversion splits the io-list
                # across consecutive direct-access records (X3.9-1978 12.9.4.2)
                vals = self._cx_expand(self._unf_values(s.items, frame))
                cells = render(items, vals, self.tgt)[0].split("\n")
            else:
                cells = [self._unf_values(s.items, frame)]
            while len(recs) < rec - 1 + len(cells):
                recs.append(None)
            for i, cell in enumerate(cells):
                recs[rec - 1 + i] = cell
            st["pos"] = rec - 1 + len(cells)
            self._set_assoc(st, frame, rec + len(cells))
            return None
        cell = recs[rec - 1] if 1 <= rec <= len(recs) else None
        if cell is not None and cell != []:  # READ an existing record
            if binmode and isinstance(cell, list):
                self._assign_words(s.items, self._binio().decode_record(cell, 0)[0], frame)
            elif items is not None and isinstance(cell, str):
                self._assign_reads(
                    s.items,
                    read_values(items, cell, self.tgt, self.free_form_input, self.character_type),
                    frame,
                )
            else:
                for ref, w in zip(self._unf_refs(s.items, frame), cell):
                    ref.write(w)
            st["pos"] = rec
            self._set_assoc(st, frame, rec + 1)
        else:
            self.last_io_error = IO_BAD_RECORD
            if "END" in s.specs:
                return Goto(s.specs["END"])
        return None

    def _is_internal_unit(self, node, frame):
        """True if an I/O unit designator is a CHARACTER entity -- an F77 internal file
        (READ/WRITE to/from its text), not an integer unit number. The unit may be a scalar
        CHARACTER variable, an array element, or a substring of either (X3.9-1978 12.2.2)."""
        if not self.character_type:
            return False
        if isinstance(node, A.Substring):  # internal file given as A(i:j)
            node = node.base
        return (
            isinstance(node, (A.Var, A.Ref))
            and self.type_of(frame.rt.unit, node.name) == "CHARACTER"
        )

    def _internal_io(self, s, frame):
        """F77 internal-file I/O (X3.9-1978 12.2.2): the 'unit' is a CHARACTER variable. WRITE
        formats the list into it per the FORMAT (fitting the record to the declared length, like
        ENCODE); READ parses its current text into the list. Scalar var = a single record; no
        device and no carriage control."""
        from forterp.fmt import read_values, render

        items = self._parsed(self._fmt_spec(s.fmt, frame))
        if s.mode == "READ":
            text = str(self.eval(s.unit, frame))
            aw = iter(self._a_field_widths(s.items, frame)) if self.character_type else None
            reads = read_values(
                items, text, self.tgt, self.free_form_input, self.character_type, aw
            )
            self._assign_reads(s.items, reads, frame)
        elif isinstance(s.unit, A.Substring):  # WRITE into a substring slice of the base
            text = render(items, self._unf_values(s.items, frame), self.tgt)[0]
            base = s.unit.base
            ref = self.arg_ref(base, frame)
            n = self.char_length(frame.rt.unit, base.name)
            cur = ref.read()
            cur = cur.ljust(n)[:n] if isinstance(cur, str) else " " * n
            lo = int(self.eval(s.unit.lo, frame)) if s.unit.lo is not None else 1
            hi = int(self.eval(s.unit.hi, frame)) if s.unit.hi is not None else n
            width = max(hi - lo + 1, 0)
            ref.write((cur[: lo - 1] + text[:width].ljust(width) + cur[hi:])[:n].ljust(n))
        else:  # WRITE: render the list, store into the CHARACTER variable (truncate / blank-pad)
            text = render(items, self._unf_values(s.items, frame), self.tgt)[0]
            n = self.char_length(frame.rt.unit, s.unit.name)
            self.arg_ref(s.unit, frame).write(text[:n].ljust(n) if n else text)
        self.last_io_error = IO_OK
        return None

    def do_io(self, s, frame):
        """READ/WRITE on a unit -- a dispatcher over the I/O forms. FileCtl, NAMELIST,
        random-access, terminal input, formatted text-file READ, formatted/sequential WRITE,
        and the unformatted-record READ each go to a handler. Returns a Goto for READ...END=
        at EOF; records are modeled as an ordered list (one statement = one record)."""
        if isinstance(s, A.FileCtl):
            return self._file_ctl(s, frame)
        if self._is_internal_unit(s.unit, frame):  # F77 internal file: the unit is a CHARACTER var
            return self._internal_io(s, frame)
        unit = int(self.eval(s.unit, frame))  # the unit number keys self.io -- coerce to int
        nml = self._nml_name(s.fmt, frame)
        if nml is not None:  # READ/WRITE(unit, NAMELIST)
            self._namelist_io(nml, s, unit, frame)
            return None
        if s.mode == "FIND" or "REC" in s.specs:  # random-access (V5 10.3.5/10.14)
            return self._random_io(s, frame, unit)
        st = self.io.get(unit)
        if st is None:
            # Auto-connect to its default device (see default_devices / V5 Table 10-1).
            dev = self.default_devices.get(unit)
            if dev is None:
                # An unconnected unit defaults to a sequential scratch file (FORTRAN-10
                # FORnn.DAT): WRITE appends value records, REWIND/BACKSPACE reposition, and a
                # later READ reads them back. Previously such writes were silently dropped.
                st = self.io[unit] = {"recs": [], "pos": 0, "mode": "w"}
            else:
                st = self.io[unit] = {"mode": dev}
        if s.mode == "READ" and st.get("mode") == "term":  # terminal input (e.g. unit 5)
            self._term_read_advance()  # FOROTS completes the pending output line before reading
            raw = self.readline()
            line = raw.rstrip("\r\n")
            self._last_input = line
            # readline() returns "" only at end-of-input; CONTROL-Z is the in-band EOF mark
            if raw == "" or "\x1a" in line:
                self.last_io_error = IO_EOF
                if "END" in s.specs:
                    return Goto(s.specs["END"])
                raise StopExecution()
            self._apply_read_line(s, frame, line)
            self.last_io_error = IO_OK
            return None
        if s.mode == "READ" and st.get("text"):  # formatted read from a text file
            return self._read_text(s, st, frame)
        if s.mode == "WRITE":
            mode = st.get("mode")
            if mode == "term":
                self._formatted_write(s, frame)
            elif mode == "lpt":
                self._formatted_write(s, frame, self.printer)
            elif mode == "w":
                # a sequential WRITE places the record at the current position and makes it
                # the last one -- records left after a prior BACKSPACE/REWIND are dropped
                # (ANSI X3.9-1966 7.1.3.3); pos then advances. Normal writing has pos == len,
                # so this is an append.
                pos = st["pos"]
                if self.character_type and s.fmt not in (None, "*") and not st.get("dec"):
                    # F77 formatted sequential file: store rendered TEXT record(s) so that `/`
                    # (record breaks) and column positioning (X/T/widths) round-trip on read --
                    # the value-record model below cannot, since it keeps list values, not text.
                    from forterp.fmt import render

                    items = self._parsed(self._fmt_spec(s.fmt, frame))
                    values = self._cx_expand(self._unf_values(s.items, frame))
                    text, _ = render(items, values, self.tgt)
                    recs = text.split("\n")
                    st["fmt_text"] = True
                    st["recs"][pos:] = recs
                    st["pos"] = pos + len(recs)
                else:
                    rec = (
                        self._bin_words(s.items, frame)  # real FOROTS data words (type-aware)
                        if st.get("dec")
                        else self._unf_values(s.items, frame)
                    )
                    st["recs"][pos:] = [rec]
                    st["pos"] = pos + 1
            return None
        if st.get("fmt_text"):  # formatted text records (F77 formatted sequential file)
            return self._read_formatted_lines(st, s, frame)
        return self._unf_record_read(st, s, frame)

    def _namelist_io(self, nml, s, unit, frame):
        """READ/WRITE(unit, NAMELIST): write the group's name=value text to the unit's
        device, or read one record and assign the group's variables from it. `unit` is the
        already-evaluated unit number (do_io evaluated it once)."""
        st = self.io.get(unit)
        if s.mode == "WRITE":
            text = self._nml_write(nml, frame)
            if st and st.get("mode") == "w":  # file: store as a text record
                st["recs"].append(text)
            elif st and st.get("mode") == "lpt":
                self.printer(text)
            else:
                self.emit(text)  # terminal / default
            return
        if st and st.get("mode") == "r" and st.get("recs") is not None:
            pos = st.get("pos", 0)
            rec = st["recs"][pos] if pos < len(st["recs"]) else ""
            st["pos"] = pos + 1
            line = rec if isinstance(rec, str) else ""
        else:
            self._term_read_advance()  # FOROTS completes the pending output line before reading
            line = self.readline()  # terminal / default
        self._nml_read(nml, line, frame)

    def _read_formatted_lines(self, st, s, frame):
        """Formatted READ from a sequential file of TEXT records (an F77 formatted WRITE).
        Honours `/`: the format is split at each top-level slash into per-record field groups,
        and each group consumes the next record -- so multi-record write/read round-trips."""
        from .fmt import read_values

        recs = st["recs"]
        if s.fmt in (None, "*"):  # list-directed / unformatted read of a text record
            if st["pos"] >= len(recs):
                self.last_io_error = IO_EOF
                return Goto(s.specs["END"]) if "END" in s.specs else None
            line = recs[st["pos"]]
            st["pos"] += 1
            self._ld_in(line, self._unf_refs(s.items, frame))
            self.last_io_error = IO_OK
            return None
        items = self._parsed(self._fmt_spec(s.fmt, frame))
        rev = getattr(items, "rev", 0)  # FORMAT reversion restart (last top-level group)

        def split(seq):  # one field-group per record (split at each top-level `/`)
            groups = [[]]
            for it in seq:
                groups.append([]) if it.kind == "/" else groups[-1].append(it)
            return groups

        # The I/O list drives how much to read: count its element slots (a COMPLEX takes two
        # real fields). Keep consuming records -- advancing at each `/` and, when the list
        # outlasts the format, reverting to `rev` for a fresh record -- until the list is full.
        needed = sum(
            2 if ty == "COMPLEX" else 1
            for it in s.items
            for _, ty in self._item_refs_typed(it, frame)
        )
        # widthless-A field widths from the io-list (one iterator shared across the records a
        # `/`-split or reverted format spans, so the A widths stay aligned with the data)
        a_widths = iter(self._a_field_widths(s.items, frame)) if self.character_type else None
        vals, start, eof = [], 0, False
        while len(vals) < needed and not eof:
            for g in split(items[start:]):
                if st["pos"] >= len(recs):
                    eof = True
                    break
                line = recs[st["pos"]]
                st["pos"] += 1
                vals += read_values(
                    g, line, self.tgt, self.free_form_input, self.character_type, a_widths
                )
                if len(vals) >= needed:
                    break
            start = rev  # subsequent passes restart at the reversion point
        if eof and len(vals) < needed:
            self.last_io_error = IO_EOF
            if "END" in s.specs:
                return Goto(s.specs["END"])
        self._assign_reads(s.items, vals, frame)
        self.last_io_error = IO_OK
        return None

    def _unf_record_read(self, st, s, frame):
        """Read one unformatted record into the I/O list. Returns a Goto for READ...END= at
        EOF (else None); EOF sets ERRSNS status 24 / monitor 308 (V5 App H)."""
        recs = st.get("recs")
        if recs is None:
            return None
        if st["pos"] >= len(recs):
            self.last_io_error = IO_EOF
            if "END" in s.specs:
                return Goto(s.specs["END"])
            return None
        rec = recs[st["pos"]]
        st["pos"] += 1
        if st.get("dec"):  # a real FOROTS word record -> decode per declared type (REAL=dec10)
            self._assign_words(s.items, rec, frame)
        else:
            for ref, w in zip(self._unf_refs(s.items, frame), rec):
                ref.write(w)
        self.last_io_error = IO_OK  # successful read clears the status
        return None

    def _spec(self, v, frame):
        """Resolve an I/O-statement spec value: a literal int/str (or None) is used
        as-is; anything else is an expression node to evaluate in `frame`."""
        return v if (v is None or isinstance(v, (int, str))) else self.eval(v, frame)

    def _conn_specs(self, st):
        """The connection-property INQUIRE specifiers (X3.9-1978 12.10.2) for a unit's state:
        ACCESS/FORM report the connection; SEQUENTIAL/DIRECT/FORMATTED/UNFORMATTED report
        YES/NO/UNKNOWN. An unopened unit (st None / no metadata) is UNKNOWN throughout."""
        acc = st.get("access") if st else None
        form = st.get("form") if st else None
        blank = st.get("blank") if st else None

        def yn(is_it, known):
            return "YES" if is_it else ("NO" if known else "UNKNOWN")

        return {
            "ACCESS": acc or "UNKNOWN",
            "SEQUENTIAL": yn(acc == "SEQUENTIAL", acc),
            "DIRECT": yn(acc == "DIRECT", acc),
            "FORM": form or "UNKNOWN",
            "FORMATTED": yn(form == "FORMATTED", form),
            "UNFORMATTED": yn(form == "UNFORMATTED", form),
            "RECL": st.get("recl", 0) if st else 0,  # fixed record length (direct access)
            "NEXTREC": st.get("nextrec", 0) if st else 0,  # next record number (direct access)
            # blank-handling mode: the OPEN value, else NULL for a formatted connection,
            # UNDEFINED for unformatted, UNKNOWN if not connected (X3.9-1978 12.10.2).
            "BLANK": blank
            or ("UNDEFINED" if form == "UNFORMATTED" else "NULL" if form else "UNKNOWN"),
        }

    def _inquire(self, s, frame):
        """F77 INQUIRE (X3.9-1978 12.10) by FILE or by UNIT. Each output specifier names a
        variable that receives the result; the common ones are supported (EXIST / OPENED /
        NUMBER / NAMED / NAME / IOSTAT and the ACCESS / FORM connection properties via
        _conn_specs). Unmodeled specifiers are simply ignored."""
        import os

        specs = s.specs
        if "FILE" in specs:
            fspec = self._spec(specs["FILE"], frame)
            fname = self.tgt.unpack(fspec).strip() if isinstance(fspec, int) else str(fspec).strip()
            path = self._open_path(fname)
            st = next((st for st in self.io.values() if st.get("path") == path), None)
            number = next((u for u, v in self.io.items() if v.get("path") == path), -1)
            results = {
                # a file currently connected exists even if no disk file backs it yet
                # (a DIRECT-access scratch file is modeled in memory until written)
                "EXIST": os.path.exists(path) or number != -1,
                "OPENED": number != -1,
                "NUMBER": number,
                "NAMED": True,
                "NAME": fname,
            }
        else:
            unit = self._spec(specs.get("UNIT", 1), frame)
            st = self.io.get(unit)
            path = st.get("path") if st else None
            results = {
                "EXIST": True,  # a unit number is always a valid connection point
                "OPENED": st is not None,
                "NUMBER": unit,
                "NAMED": path is not None,
                "NAME": os.path.basename(path) if path else "",
            }
        results.update(self._conn_specs(st))
        results["IOSTAT"] = 0
        for key, val in results.items():
            tgt = specs.get(key)
            if not isinstance(tgt, (A.Var, A.Ref)):  # output specifiers are variables
                continue
            ref = self.arg_ref(tgt, frame)
            if isinstance(val, bool):
                ref.write(self.tgt.from_bool(val))
            elif isinstance(val, str):
                n = self.char_length(frame.rt.unit, tgt.name)
                ref.write(val[:n].ljust(n) if n else val)
            else:
                ref.write(val)
        return None

    def _file_ctl(self, s, frame):
        import json
        import os

        specs = s.specs
        if s.verb == "INQUIRE":
            return self._inquire(s, frame)
        unit = self._spec(specs.get("UNIT", 1), frame)
        if s.verb == "OPEN":
            dev = specs.get("DEVICE")
            if isinstance(dev, str) or dev is None:
                devname = dev or ""
            else:
                dv = self.eval(dev, frame)
                devname = self.tgt.unpack(dv).strip() if isinstance(dv, int) else str(dv).strip()
            access = specs.get("ACCESS")
            form_kw = specs.get("FORM") if isinstance(specs.get("FORM"), str) else None
            assoc = specs.get("ASSOCIATEVARIABLE")
            assoc_name = (
                assoc.name
                if isinstance(assoc, A.Var)
                else assoc
                if isinstance(assoc, str)
                else None
            )
            if (
                access in ("RANDOM", "DIRECT") or assoc_name is not None
            ):  # random/direct (V5 10.3.5)
                fspec = specs.get("FILE") or specs.get("NAME")  # the name for INQUIRE(FILE=)/reload
                path = None
                if fspec is not None:
                    v = self._spec(fspec, frame)
                    fname = self.tgt.unpack(v).strip() if isinstance(v, int) else str(v).strip()
                    path = self._open_path(fname)
                status_kw = specs.get("STATUS")
                status_kw = status_kw.upper() if isinstance(status_kw, str) else None
                st = self.io.get(unit)
                if st is None:
                    # reconnect to a direct-access file CLOSEd earlier (STATUS='OLD' reopen):
                    # reload its records from disk; STATUS='NEW' always starts fresh
                    if path and os.path.exists(path) and status_kw != "NEW":
                        st = self.io[unit] = self._open_read_unit(path)
                    else:
                        st = self.io[unit] = {"recs": [], "pos": 0}
                st["mode"] = "random"
                st["access"], st["form"] = "DIRECT", form_kw or "UNFORMATTED"  # INQUIRE metadata
                st.setdefault("nextrec", 1)  # INQUIRE(NEXTREC=) -- record 1 until I/O moves it
                if "RECL" in specs:  # INQUIRE(RECL=) -- the fixed record length
                    st["recl"] = int(self._spec(specs["RECL"], frame))
                if path is not None:
                    st["path"] = path
                if "BLANK" in specs:  # INQUIRE(BLANK=) -- blank-handling mode (NULL / ZERO)
                    bl = self._spec(specs["BLANK"], frame)
                    st["blank"] = (
                        self.tgt.unpack(bl).strip() if isinstance(bl, int) else str(bl).strip()
                    )
                mode_kw = specs.get("MODE")  # 'BINARY' -> FOROTS words
                if isinstance(mode_kw, str) and mode_kw.upper() == "BINARY":
                    st["binary"] = True
                if assoc_name:
                    st["assoc"] = assoc_name
                    self._set_assoc(st, frame, 1)
                return None
            handler = self.device_handlers.get(devname)
            if handler is not None:  # a registered device (e.g. GAM:)
                handler(self, unit, specs, frame)
            elif devname == "TTY":
                self.io[unit] = {"mode": "term"}  # block printout -> terminal
            else:
                fspec = self._spec(specs.get("FILE") or specs.get("NAME") or "EMPIRE.DAT", frame)
                # a numeric file spec is a packed SIXBIT/ASCII filename (FORTRAN-10) -- decode it
                # the same way DEVICE is, so OPEN(...FILE=<packed word>...) resolves to its name.
                # Strip either form: a CHARACTER filename is blank-padded and INQUIRE(FILE=) also
                # strips, so they must agree on the path or INQUIRE-by-file won't find the unit.
                fname = (
                    self.tgt.unpack(fspec).strip() if isinstance(fspec, int) else str(fspec).strip()
                )
                path = self._open_path(fname)
                if access == "SEQOUT":
                    self.io[unit] = {
                        "recs": [],
                        "pos": 0,
                        "mode": "w",
                        "path": path,
                        "dec": self.forots,
                    }
                elif access == "SEQIN" or os.path.exists(path):
                    self.io[unit] = self._open_read_unit(path)
                else:  # F77 sequential connection to a not-yet-existing file -> empty scratch
                    self.io[unit] = {"recs": [], "pos": 0, "mode": "w", "path": path}
                st = self.io[unit]  # record INQUIRE metadata for the connection
                st["access"] = "SEQUENTIAL"
                st["form"] = form_kw or "FORMATTED"
                if "BLANK" in specs:  # INQUIRE(BLANK=) -- blank-handling mode (NULL / ZERO)
                    bl = self._spec(specs["BLANK"], frame)
                    st["blank"] = (
                        self.tgt.unpack(bl).strip() if isinstance(bl, int) else str(bl).strip()
                    )
            return None
        if s.verb == "CLOSE":
            st = self.io.pop(unit, None)
            status = specs.get("STATUS")
            if status is not None:
                sv = self._spec(status, frame)
                status = (
                    self.tgt.unpack(sv).strip() if isinstance(sv, int) else str(sv).strip()
                ).upper()
            path = st.get("path") if st else None
            if status == "DELETE":  # discard the file rather than persist it (12.10.1)
                if path and os.path.exists(path):
                    os.remove(path)
            # persist a written file so a later OPEN can reconnect: sequential output ("w") and
            # a direct-access file ("random") both serialize their record list to disk on CLOSE
            elif st and path and st.get("recs") is not None and st.get("mode") in ("w", "random"):
                if st.get("dec"):  # real FOROTS binary: LSCW-framed words, core-dumped to bytes
                    with open(path, "wb") as fh:
                        fh.write(self._binio().encode_binary_file(st["recs"]))
                else:
                    with open(path, "w") as fh:
                        json.dump(st["recs"], fh)
            return None
        # device control: REWIND / BACKSPACE / ENDFILE / SKIP RECORD / SKIP FILE
        st = self.io.get(unit)
        if st is not None and "pos" in st:
            recs = st.setdefault("recs", [])
            if s.verb == "REWIND":
                st["pos"] = 0
            elif s.verb == "BACKSPACE":
                st["pos"] = max(0, st["pos"] - 1)
            elif s.verb == "ENDFILE":
                del recs[st["pos"] :]  # write end-of-file at current pos
            elif s.verb == "SKIPREC":
                st["pos"] = min(len(recs), st["pos"] + 1)
            elif s.verb == "SKIPFILE":
                st["pos"] = len(recs)
        return None

    def _open_read_unit(self, path):
        """Open an existing file for sequential read, detecting its on-disk form: a real
        FOROTS binary file (core-dump words; only when `forots`) -> word-list records; our
        JSON record list (the portable default and legacy saves); else ordinary text data."""
        import json

        try:
            with open(path, "rb") as fh:
                raw = fh.read()
        except OSError:  # missing/empty -> an empty unit (a fresh READ hits END=)
            return {"recs": [], "pos": 0, "mode": "r", "path": path}
        if raw[:1] == b"\x00":  # a core-dump START LSCW begins 0x00 -> this is a FOROTS binary file
            if not self.forots:  # config mismatch: a binary file, unit not in dec mode
                raise OSError(
                    f"{path}: looks like a FOROTS binary file, but this unit is not in binary "
                    "mode (forots off) -- refusing to read it as garbage text"
                )
            try:
                recs = self._binio().decode_binary_file(raw)
            except ValueError as e:  # NUL-led but won't parse: truncated/corrupt, not silent text
                raise OSError(f"{path}: not a valid FOROTS binary file ({e})") from e
            return {"recs": recs, "pos": 0, "mode": "r", "path": path, "dec": True}
        try:  # our portable form / legacy saves: a JSON record list
            return {"recs": json.loads(raw or b"[]"), "pos": 0, "mode": "r", "path": path}
        except ValueError:  # not JSON -> a formatted text data file
            return {
                "lines": raw.decode(errors="replace").splitlines(),
                "pos": 0,
                "mode": "r",
                "text": True,
                "path": path,
            }

    def _open_path(self, name):
        """Resolve an OPEN file-spec to a host path relative to save_root: try the name
        as given, then a .DAT default (TOPS-10), then a case-insensitive match.

        NOTE: save_root is a BASE DIRECTORY for relative names, not a security boundary.
        forterp runs the program's file I/O against the real filesystem -- an absolute path
        or one with `..` reaches outside save_root. forterp is an interpreter, not a sandbox;
        do not run untrusted source expecting containment."""
        import os

        cand = os.path.join(self.save_root, name)
        if os.path.exists(cand):
            return cand
        if "." not in name and os.path.exists(cand + ".DAT"):
            return cand + ".DAT"
        low = name.lower()
        try:
            for f in os.listdir(self.save_root):
                if f.lower() in (low, low + ".dat"):
                    return os.path.join(self.save_root, f)
        except OSError:
            pass
        return cand

    def _read_text(self, s, st, frame):
        """Formatted/list-directed READ from a text file unit: read
        the next line and parse it per the FORMAT (or by tokens if list-directed)."""
        from .fmt import read_values

        lines = st["lines"]
        if st["pos"] >= len(lines):
            self.last_io_error = IO_EOF
            return Goto(s.specs["END"]) if "END" in s.specs else None
        line = lines[st["pos"]]
        st["pos"] += 1
        if s.fmt is None or s.fmt == "*":
            self._ld_in(line, self._unf_refs(s.items, frame))
        else:
            spec = self._fmt_spec(s.fmt, frame)
            items = self._parsed(spec)
            self._assign_reads(
                s.items,
                read_values(items, line, self.tgt, self.free_form_input, self.character_type),
                frame,
            )
        self.last_io_error = IO_OK
        return None

    def _unf_values(self, items, frame):
        return [r.read() for it in items for r in self._item_refs(it, frame)]

    def _unf_refs(self, items, frame):
        return [r for it in items for r in self._item_refs(it, frame)]

    def _item_refs_typed(self, it, frame):
        """(ref, declared-type-name) for each element of one I/O-list item, following array
        and implied-DO expansion. The per-element type drives FOROTS binary word coding
        (REAL = one DEC-10 single, DOUBLE PRECISION = a two-word double, COMPLEX = two
        singles, INTEGER/LOGICAL = one word) and complex's two-reals-per-element formatted
        transfer (V5 Ch4). Resolving the type per element keeps it correct inside an
        implied-DO -- (D(I),I=1,N) over a DOUBLE PRECISION array reports DOUBLE, not the
        loop index's INTEGER type."""
        unit = frame.rt.unit
        if isinstance(it, A.Var) and it.name in unit.arrays:
            ty = self.type_of(unit, it.name)
            view = self.arrayview(frame, it.name)
            return [(view.loc(i), ty) for i in range(array_size(unit.arrays[it.name]))]
        if isinstance(it, A.ImpliedDo):
            out = []
            lo = self.eval(it.start, frame)
            hi = self.eval(it.stop, frame)
            step = self.eval(it.step, frame) if it.step else 1
            vref = self.scalar_ref(frame, it.var)
            i = lo
            while (step > 0 and i <= hi) or (step < 0 and i >= hi):
                vref.write(i)
                for sub in it.items:
                    out.extend(self._item_refs_typed(sub, frame))
                i += step
            return out
        ty = self.type_of(unit, it.name) if isinstance(it, (A.Var, A.Ref)) else "INTEGER"
        return [(self.arg_ref(it, frame), ty)]

    def _a_field_widths(self, items, frame):
        """Per formatted-input FIELD (in transfer order, COMPLEX = two fields), the width a
        widthless A should read: a CHARACTER element's declared length, else None. A widthless
        A descriptor under the F77 CHARACTER model reads that many columns of the list item
        (X3.9-1978 13.5.11) -- the field count aligns 1:1 with read_values' value-producing
        descriptors, so the reader pops one entry per field."""
        unit = frame.rt.unit
        out = []

        def width(name):
            ty = self.type_of(unit, name)
            if ty == "COMPLEX":
                return [None, None]
            return [self.char_length(unit, name) if ty == "CHARACTER" else None]

        def walk(it):
            if isinstance(it, A.ImpliedDo):
                lo = self.eval(it.start, frame)
                hi = self.eval(it.stop, frame)
                step = self.eval(it.step, frame) if it.step else 1
                i = lo
                while (step > 0 and i <= hi) or (step < 0 and i >= hi):
                    for sub in it.items:
                        walk(sub)
                    i += step
            elif isinstance(it, A.Var) and it.name in unit.arrays:
                w = width(it.name)
                out.extend(w * array_size(unit.arrays[it.name]))
            elif isinstance(it, (A.Var, A.Ref)):
                out.extend(width(it.name))
            else:
                out.append(None)  # an expression (output only)

        for it in items:
            walk(it)
        return out

    def _bin_words(self, items, frame):
        """Encode the I/O list's values to FOROTS data words per declared type (V5 D.5.2):
        REAL -> one DEC-10 single; DOUBLE PRECISION -> a two-word double (62-bit fraction);
        COMPLEX -> two singles (re, im); INTEGER/LOGICAL -> one two's-complement word."""
        bn = self._binio()
        words = []
        for it in items:
            for ref, ty in self._item_refs_typed(it, frame):
                v = ref.read()
                if ty == "DOUBLE PRECISION":
                    words += list(bn.double_to_dec10_pair(float(v)))
                elif ty == "COMPLEX" or isinstance(v, complex):
                    c = v if isinstance(v, complex) else complex(float(v), 0.0)
                    words += [bn.double_to_dec10(c.real), bn.double_to_dec10(c.imag)]
                elif isinstance(v, float):
                    words.append(bn.double_to_dec10(v))
                else:
                    words.append(self.tgt.wrap(int(v)))
        return words

    def _assign_words(self, items, words, frame):
        """Assign FOROTS binary data words to the I/O list, decoding each per the target's
        declared type: REAL -> one DEC-10 single; DOUBLE PRECISION -> a two-word double;
        COMPLEX -> two singles; INTEGER/LOGICAL -> one two's-complement word."""
        bn = self._binio()
        wi = iter(words)
        for it in items:
            for ref, ty in self._item_refs_typed(it, frame):
                try:
                    w = next(wi)
                except StopIteration:
                    return  # record exhausted: leave the remaining list items untouched
                if ty == "DOUBLE PRECISION":
                    ref.write(bn.dec10_pair_to_double(w, next(wi, 0)))
                elif ty == "COMPLEX":
                    ref.write(complex(bn.dec10_to_double(w), bn.dec10_to_double(next(wi, 0))))
                elif ty == "REAL":
                    ref.write(bn.dec10_to_double(w))
                else:
                    ref.write(self.tgt.wrap(w))  # integer/logical: 2's-complement value

    def _assign_reads(self, items, reads, frame):
        """Write formatted-input values to the I/O list. A COMPLEX target consumes
        two consecutive real fields -> complex(re, im) (V5 Ch4)."""
        vals = iter(v for (_, v) in reads)
        for it in items:
            name = getattr(it, "name", None)  # the I/O-list item's name (for CHARACTER length)
            for ref, ty in self._item_refs_typed(it, frame):
                try:
                    v = next(vals)
                except StopIteration:
                    return
                if ty == "COMPLEX" and not isinstance(v, complex):
                    v = complex(float(v), float(next(vals, 0.0)))
                elif ty == "CHARACTER" and isinstance(v, str):
                    # F77 A input (X3.9-1978 13.5.11): a field wider than the variable supplies
                    # its rightmost chars; a narrower field is left-justified, blank-filled.
                    n = self.char_length(frame.rt.unit, name) if name else len(v)
                    v = (v[-n:] if len(v) > n else v.ljust(n)) if n else v
                ref.write(v)

    def _item_refs(self, it, frame):
        """Flatten one I/O list item into element references (whole arrays
        expand to all elements; implied-DO expands its range)."""
        if isinstance(it, A.Var) and it.name in frame.rt.unit.arrays:
            view = self.arrayview(frame, it.name)
            return [view.loc(i) for i in range(array_size(frame.rt.unit.arrays[it.name]))]
        if isinstance(it, A.ImpliedDo):
            refs = []
            lo = self.eval(it.start, frame)
            hi = self.eval(it.stop, frame)
            step = self.eval(it.step, frame) if it.step else 1
            vref = self.scalar_ref(frame, it.var)
            i = lo
            while (step > 0 and i <= hi) or (step < 0 and i >= hi):
                vref.write(i)
                for sub in it.items:
                    refs.extend(self._item_refs(sub, frame))
                i += step
            return refs
        return [self.arg_ref(it, frame)]

    @staticmethod
    def _show(v):
        return str(v)


def _lsh(tgt, v, n):
    """Logical (unsigned) word shift; n<0 shifts right. The word width is the
    target's (PDP-10: 36-bit two's-complement); a target with no fixed width
    (mask falsy) does an unmasked Python shift."""
    u = int(v)
    if tgt.mask:
        u &= tgt.mask
    u = (u << n) if n >= 0 else (u >> -n)
    if tgt.mask:
        u &= tgt.mask
    return tgt.wrap(u)


def _rot(tgt, v, n):
    """Logical word ROTATE left by n bits (n<0 rotates right), within the target's word
    width (V5). A target with no fixed width (mask falsy) can't rotate -> returns v."""
    if not tgt.mask:
        return tgt.wrap(int(v))
    w = tgt.word_bits
    u = int(v) & tgt.mask
    n %= w  # normalize; a negative (right) rotate becomes the equivalent left rotate
    u = ((u << n) | (u >> (w - n))) & tgt.mask if n else u
    return tgt.wrap(u)


def _anint(x):  # round to nearest whole, halves away from zero
    return float(math.floor(x + 0.5)) if x >= 0 else float(math.ceil(x - 0.5))


# FORTRAN-10 V5 Appendix H, Table H-2: exact FOROTS message text for the math
# LIB domain errors, plus the recovery value each returns after the warning.
_LIB_MSG = {
    "SQRT": "Attempt to take SQRT of Negative Arg.",
    "DSQRT": "Attempt to take DSQRT of Negative Arg.",
    "ALOG": "Attempt to take LOG of Negative Arg.",
    "ALOG10": "Attempt to take LOG of Negative Arg.",
    "DLOG": "Attempt to take DLOG of Negative Arg.",
    "DLOG10": "Attempt to take DLOG of Negative Arg.",
    "ASIN": "ASIN of Arg. > 1.0 in Magnitude",
    "ACOS": "ACOS of Arg. > 1.0 in Magnitude",
}


def _rec_log(a):  # log on |x|; log of 0 -> 0.0 (avoid -inf)
    x = abs(a[0])
    return math.log(x) if x > 0 else 0.0


def _rec_log10(a):
    x = abs(a[0])
    return math.log10(x) if x > 0 else 0.0


_LIB_RECOVER = {
    "SQRT": lambda a: math.sqrt(abs(a[0])),
    "DSQRT": lambda a: math.sqrt(abs(a[0])),
    "ALOG": _rec_log,
    "ALOG10": _rec_log10,
    "DLOG": _rec_log,
    "DLOG10": _rec_log10,
    "ASIN": lambda a: math.asin(max(-1.0, min(1.0, a[0]))),
    "ACOS": lambda a: math.acos(max(-1.0, min(1.0, a[0]))),
}


_INT_RESULT = frozenset({"INT", "IFIX", "IDINT", "NINT", "IDNINT"})  # take the target's int wrap

# F77 generic dispatch: a generic transcendental called with a COMPLEX argument resolves to the
# complex (cmath) variant. The real/double cases already go through math.* (REAL is a Python
# double here); only complex needs redirecting. ABS/MAX/MIN are already polymorphic (Python
# abs/max/min), so they need no entry. (CLOG10 has no FOROTS name; LOG10 of complex is unused.)
_COMPLEX_GENERIC = {
    "SQRT": "CSQRT",
    "EXP": "CEXP",
    "LOG": "CLOG",
    "ALOG": "CLOG",
    "SIN": "CSIN",
    "COS": "CCOS",
}

# F77 lexical-comparison intrinsics (X3.9-1978 15.10): compare two CHARACTER values on the
# ASCII collating sequence, blank-padded to equal length, returning a logical.
_CHAR_LOGICAL = {
    "LGE": lambda a, b: a >= b,
    "LGT": lambda a, b: a > b,
    "LLE": lambda a, b: a <= b,
    "LLT": lambda a, b: a < b,
}

# The ANSI X3.9-1966 standard library: Table 3 (intrinsic) + Table 4 (basic external), 55
# functions. Everything else in INTRINSICS (TAN, NINT/ANINT, the DTAN.../TAND... families,
# LSH, MAX/MIN, ...) is a DEC/F77 extension, exposed only when the dialect's dec_intrinsics
# is on (FORTRAN10, or an F66 dialect that opts in).
_F66_INTRINSICS = frozenset(
    # Table 3 (31 intrinsic functions)
    "ABS IABS DABS AINT INT IDINT AMOD MOD AMAX0 AMAX1 MAX0 MAX1 DMAX1 AMIN0 AMIN1 MIN0 "
    "MIN1 DMIN1 FLOAT IFIX SIGN ISIGN DSIGN DIM IDIM SNGL REAL AIMAG DBLE CMPLX CONJG "
    # Table 4 (24 basic external functions)
    "EXP DEXP CEXP ALOG DLOG CLOG ALOG10 DLOG10 SIN DSIN CSIN COS DCOS CCOS TANH SQRT "
    "DSQRT CSQRT ATAN DATAN ATAN2 DATAN2 DMOD CABS".split()
)

INTRINSICS = {
    # ---- DEC extensions ----
    "LSH": lambda a: _lsh(PDP10, a[0], a[1]),  # width-dependent; routed via self.tgt
    "ROT": lambda a: _rot(PDP10, a[0], a[1]),  # width-dependent; routed via self.tgt
    # ---- type conversion (INT-family wrap applied target-aware in _apply_intrinsic) ----
    "INT": lambda a: int(a[0]),
    "IFIX": lambda a: int(a[0]),
    "IDINT": lambda a: int(a[0]),
    "FLOAT": lambda a: float(a[0]),
    "FLOATR": lambda a: float(a[0]),
    "SNGL": lambda a: float(a[0]),
    "REAL": lambda a: a[0].real if isinstance(a[0], complex) else float(a[0]),
    # ---- COMPLEX (V5 Ch4/Table 15-1; values are Python complex) ----
    "CMPLX": lambda a: complex(a[0], a[1] if len(a) > 1 else 0.0),
    "DCMPLX": lambda a: complex(a[0], a[1] if len(a) > 1 else 0.0),
    "AIMAG": lambda a: a[0].imag if isinstance(a[0], complex) else 0.0,
    "CONJG": lambda a: a[0].conjugate() if isinstance(a[0], complex) else complex(a[0]),
    "CABS": lambda a: abs(a[0]),
    "CSQRT": lambda a: cmath.sqrt(a[0]),
    "CEXP": lambda a: cmath.exp(a[0]),
    "CLOG": lambda a: cmath.log(a[0]),
    "CSIN": lambda a: cmath.sin(a[0]),
    "CCOS": lambda a: cmath.cos(a[0]),
    "TIM2GO": lambda a: 1.0e9,  # CPU time remaining (V5 Table 15-2): effectively unlimited
    "DBLE": lambda a: float(a[0]),
    "AINT": lambda a: float(int(a[0])),  # truncate toward zero
    "ANINT": lambda a: _anint(a[0]),
    "NINT": lambda a: int(_anint(a[0])),
    # ---- absolute value / sign / difference ----
    "ABS": lambda a: abs(a[0]),
    "IABS": lambda a: abs(int(a[0])),
    "DABS": lambda a: abs(a[0]),
    "SIGN": lambda a: abs(a[0]) if a[1] >= 0 else -abs(a[0]),
    "ISIGN": lambda a: abs(int(a[0])) if a[1] >= 0 else -abs(int(a[0])),
    "DSIGN": lambda a: abs(a[0]) if a[1] >= 0 else -abs(a[0]),
    "DIM": lambda a: max(a[0] - a[1], 0),
    "IDIM": lambda a: max(int(a[0]) - int(a[1]), 0),
    # ---- remaindering ----
    "MOD": lambda a: fort_mod(a[0], a[1]),
    "AMOD": lambda a: fort_mod(float(a[0]), float(a[1])),
    "DMOD": lambda a: fort_mod(float(a[0]), float(a[1])),
    # ---- max / min (all F66 typed variants + generic) ----
    "MAX0": lambda a: max(int(x) for x in a),
    "MIN0": lambda a: min(int(x) for x in a),
    "MAX1": lambda a: int(max(float(x) for x in a)),
    "MIN1": lambda a: int(min(float(x) for x in a)),
    "AMAX0": lambda a: float(max(int(x) for x in a)),
    "AMIN0": lambda a: float(min(int(x) for x in a)),
    "AMAX1": lambda a: max(float(x) for x in a),
    "AMIN1": lambda a: min(float(x) for x in a),
    "MAX": lambda a: max(a),
    "MIN": lambda a: min(a),
    # ---- square root / exponential / logarithm ----
    "SQRT": lambda a: math.sqrt(a[0]),
    "DSQRT": lambda a: math.sqrt(a[0]),
    "EXP": lambda a: math.exp(a[0]),
    "DEXP": lambda a: math.exp(a[0]),
    "ALOG": lambda a: math.log(a[0]),
    "DLOG": lambda a: math.log(a[0]),
    "ALOG10": lambda a: math.log10(a[0]),
    "DLOG10": lambda a: math.log10(a[0]),
    "LOG": lambda a: math.log(a[0]),  # F77 generic natural log (F66 spelled it ALOG)
    "LOG10": lambda a: math.log10(a[0]),  # F77 generic common log (F66: ALOG10)
    # ---- F77 CHARACTER (operands/results are Python str under the character_type dialect) ----
    "LEN": lambda a: len(a[0]),  # declared length (fixed-length vars are stored blank-padded)
    "CHAR": lambda a: chr(int(a[0]) & 0x7F),  # ASCII code -> the 1-character string
    "ICHAR": lambda a: ord(a[0][0]) if a[0] else 0,  # 1st char -> its ASCII code
    "INDEX": lambda a: a[0].find(a[1]) + 1,  # 1-based position of a[1] in a[0] (0 = not found)
    # ---- trigonometric / hyperbolic ----
    "SIN": lambda a: math.sin(a[0]),
    "DSIN": lambda a: math.sin(a[0]),
    "COS": lambda a: math.cos(a[0]),
    "DCOS": lambda a: math.cos(a[0]),
    "TAN": lambda a: math.tan(a[0]),
    "ATAN": lambda a: math.atan(a[0]),
    "DATAN": lambda a: math.atan(a[0]),
    "ATAN2": lambda a: math.atan2(a[0], a[1]),
    "DATAN2": lambda a: math.atan2(a[0], a[1]),
    "SINH": lambda a: math.sinh(a[0]),
    "COSH": lambda a: math.cosh(a[0]),
    "TANH": lambda a: math.tanh(a[0]),
    "SIND": lambda a: math.sin(math.radians(a[0])),  # sine of degrees
    "COSD": lambda a: math.cos(math.radians(a[0])),  # cosine of degrees
    "ASIN": lambda a: math.asin(a[0]),
    "ACOS": lambda a: math.acos(a[0]),
    "DTAN": lambda a: math.tan(a[0]),
    "DASIN": lambda a: math.asin(a[0]),
    "DACOS": lambda a: math.acos(a[0]),
    "DSINH": lambda a: math.sinh(a[0]),
    "DCOSH": lambda a: math.cosh(a[0]),
    "DTANH": lambda a: math.tanh(a[0]),
    # ---- degree-argument trig (V5): argument/result in degrees ----
    "TAND": lambda a: math.tan(math.radians(a[0])),
    "ASIND": lambda a: math.degrees(math.asin(a[0])),
    "ACOSD": lambda a: math.degrees(math.acos(a[0])),
    "ATAND": lambda a: math.degrees(math.atan(a[0])),
    "ATAN2D": lambda a: math.degrees(math.atan2(a[0], a[1])),
    "DSIND": lambda a: math.sin(math.radians(a[0])),
    "DCOSD": lambda a: math.cos(math.radians(a[0])),
    "DTAND": lambda a: math.tan(math.radians(a[0])),
    # ---- double-precision variants (we model double as Python float) ----
    "DFLOAT": lambda a: float(a[0]),  # integer -> double
    "DINT": lambda a: float(int(a[0])),  # truncate toward zero
    "DNINT": lambda a: _anint(a[0]),  # round to nearest whole
    "IDNINT": lambda a: int(_anint(a[0])),  # round to nearest integer
    "DDIM": lambda a: max(a[0] - a[1], 0),  # positive difference
    "DPROD": lambda a: float(a[0]) * float(a[1]),  # double product of two reals
    "DMAX1": lambda a: max(float(x) for x in a),
    "DMIN1": lambda a: min(float(x) for x in a),
}


class StopExecution(Exception):
    pass
