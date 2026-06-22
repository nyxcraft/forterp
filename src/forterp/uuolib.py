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
        text = eng.tgt.unpack(int(eng.eval(node, frame)), 5).rstrip()
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


def b_GETTAB(eng, frame, arg_nodes):
    """GETTAB(...) -- read a monitor table word (CALLI GETTAB). Returns 0 with no monitor tables
    modeled; a monitor layer that does model them registers its own GETTAB to override this."""
    return 0


#: the standard monitor UUOs, registered by install_runtime under the FORTRAN-10 dialect
UUOLIB = {
    "OUTSTR": b_OUTSTR,
    "OUTCHR": b_OUTCHR,
    "MSTIME": b_MSTIME,
    "SLEEP": b_SLEEP,
    "GETTAB": b_GETTAB,
}
