"""Standard TOPS-10 monitor UUOs callable from FORTRAN-10.

Programmed operators a DECsystem-10 program issues for terminal I/O, the clock, and timing.
These are NOT the FORTRAN-10 V5 library (that is `forlib.STDLIB`, the manual's Ch15 table) -- they
are the monitor facilities the runtime environment provided, so a program that `CALL`s `OUTSTR`/
`MSTIME`/`SLEEP` just runs without bundling its own glue. Installed (like `STDLIB`) only under the
FORTRAN-10 dialect, and never shadowing a routine the program -- or its host -- defines itself, so
a host can register a richer/translated variant (e.g. a terminal-aware `OUTCHR`, or a real
`GETTAB` over monitor tables) that wins by registering after the runtime.

Each routine reads the host seam off the engine directly -- `eng.emit` (terminal), `eng.clock`
(the ms clock the driver supplies), `eng.tgt` (the value-model codec) -- the same way `STDLIB`
does, so behavior stays an injected input, never an ambient read.
"""

from __future__ import annotations

from forterp.ast import StrLit
from forterp.forlib import _needs


@_needs(1)
def b_OUTSTR(eng, frame, arg_nodes):
    """OUTSTR(STR) -- write a string to the controlling terminal (TTCALL OUTSTR)."""
    node = arg_nodes[0]
    if isinstance(node, StrLit):
        text = node.value
    else:  # a packed word -> its chars (blank/null padding trimmed)
        text = eng.tgt.unpack(int(eng.eval(node, frame)), eng.tgt.chars_per_word).rstrip()
    eng.emit(text)


@_needs(1)
def b_OUTCHR(eng, frame, arg_nodes):
    """OUTCHR(CH) -- write one character (low 7 bits) to the terminal (TTCALL OUTCHR)."""
    eng.emit(chr(int(eng.eval(arg_nodes[0], frame)) & 0x7F))


@_needs(1)
def b_MSTIME(eng, frame, arg_nodes):
    """MSTIME(T) -- the job's millisecond runtime clock, returned into T by reference."""
    eng.arg_ref(arg_nodes[0], frame).write(eng.clock)


def b_SLEEP(eng, frame, arg_nodes):
    """SLEEP(SECS) -- suspend the job (HIBER/SLEEP UUO). A no-op under the interpreter; there is
    no job to stall, and nothing observable changes."""
    return 0


class UnmodeledMonitorTable(Exception):
    """GETTAB requested a monitor table forterp doesn't model. Raised instead of silently
    returning a (likely wrong) 0: an unmodeled table is a gap, not a value, so it fails loud.
    Resolve it by modeling the table in GETTAB, registering ``eng.gettab[table]``, or catching
    this at the driver/CLI if the program tolerates the missing table."""

    def __init__(self, table, item):
        self.table, self.item = table, item
        super().__init__(
            f"GETTAB table {table} (item {item}) is not modeled -- returning a value here would "
            f"be a blind guess. Model it in forterp's GETTAB, set eng.gettab[{table}], or catch "
            f"UnmodeledMonitorTable at the driver if the program tolerates a missing table."
        )


_GUEST_PPN = 0  # [0,0] -- TOPS-10's null PPN; the neutral "no account" identity forterp reports

# The GETTAB (table, item) queries forterp answers itself, each the faithful generic value for any
# forterp job (verified .GTxxx names from UUOSYM.MAC). A host overrides/adds tables via eng.gettab;
# any table not here and not registered raises UnmodeledMonitorTable rather than guessing 0.
_GETTAB_DEFAULTS = {
    (2, -1): _GUEST_PPN,  # .GTPPN -- this job's proj-prog number; guest [0,0] (no real login)
    (0o120, -1): 0,  # .GTJTC -- job scheduler type/class (JBTSCD); 0 = unclassed (no class sched)
}


def b_GETTAB(eng, frame, arg_nodes):
    """GETTAB(TABLE,ITEM) -- read a monitor table word (CALLI GETTAB).

    Resolution order: an embedder's per-table registry (``eng.gettab`` -- ``{table: value | (eng,
    item)->value}``) wins, so a host maps the tables it cares about as it sees fit; then the
    queries forterp answers itself (`_GETTAB_DEFAULTS`): .GTPPN(2,-1) -> the null/guest PPN [0,0]
    (forterp does not presume a real login), and .GTJTC(120,-1) -> 0 (no class scheduler, so the
    job is unclassed). Any *other* table raises `UnmodeledMonitorTable` rather than guessing 0.

    To report a real (or privileged) identity, register `eng.gettab[2]` -- the host owns that
    mapping, including any REAL type-pun (GETTAB returns whatever the registry yields verbatim).
    The host identity is available as `mon.identity` for a host that wants to map it in."""
    table = int(eng.eval(arg_nodes[0], frame)) if arg_nodes else 0
    item = int(eng.eval(arg_nodes[1], frame)) if len(arg_nodes) > 1 else 0
    tables = getattr(eng, "gettab", None)  # embedder-registered table handlers
    if tables and table in tables:
        handler = tables[table]
        return handler(eng, item) if callable(handler) else handler
    if (table, item) in _GETTAB_DEFAULTS:
        return _GETTAB_DEFAULTS[(table, item)]
    raise UnmodeledMonitorTable(table, item)


#: the standard monitor UUOs, registered by install_runtime under the FORTRAN-10 dialect
UUOLIB = {
    "OUTSTR": b_OUTSTR,
    "OUTCHR": b_OUTCHR,
    "MSTIME": b_MSTIME,
    "SLEEP": b_SLEEP,
    "GETTAB": b_GETTAB,
}
