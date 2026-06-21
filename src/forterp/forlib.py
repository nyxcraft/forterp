"""The standard FORTRAN-10 V5 library subroutines (manual Ch15 Table 15-3 /
Appendix H).

These ship WITH the interpreter -- they are part of "being FORTRAN-10 V5", not
part of any one host/driver. A host program registers them via
`eng.register_builtins(STDLIB)` alongside its own external routines. The
environment-dependent ones read services off the engine that the host controls --
notably the clock provider `eng.now()` -- so wall-time/error behavior is an injected
input, never an ambient read. This is the formal split: interpreter = language +
standard runtime; host = environment.

Implemented here: TIME, DATE (read eng.now), EXIT, ERRSNS, ERRSET (read/write the
engine's FOROTS error state). Each has the builtin signature (eng, frame, arg_nodes).
"""

from __future__ import annotations

from forterp.engine import StopExecution

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _store_words(eng, ref, text):
    """Write `text` as consecutive packed-ASCII words (chars_per_word, left-justified)
    into a target that may be a scalar ref (.write) or an array view (.loc(i))."""
    cw = eng.tgt.chars_per_word
    words = [eng.tgt.pack(text[i : i + cw].ljust(cw)) for i in range(0, max(len(text), 1), cw)]
    if hasattr(ref, "loc"):  # array argument (e.g. DATE's 2-word array)
        for i, w in enumerate(words):
            ref.loc(i).write(w)
    else:  # scalar argument (e.g. TIME's 1 word)
        ref.write(words[0])


def _fmt_date(t):
    """V5 Table 15-3 DATE: 'dd-mmm-yy'. dd = 2-digit day with a LEADING ZERO shown
    as a blank (f'{d:2d}' gives exactly that); mmm = 3-letter month, mixed case
    ('Mar'); yy = 2-digit year."""
    y, m, d = t[0], t[1], t[2]
    return f"{d:2d}-{_MONTHS[(m - 1) % 12]}-{y % 100:02d}"


def _fmt_time(t):
    """V5 Table 15-3 TIME, one-arg form: 'hh:mm' (24-hour)."""
    return f"{t[3]:02d}:{t[4]:02d}"


def _fmt_time2(t):
    """V5 Table 15-3 TIME, second arg: 'bss.t' (blank, seconds, '.', tenths)."""
    return f" {t[5]:02d}.{t[6] % 10:1d}"


def b_TIME(eng, frame, arg_nodes):
    """CALL TIME(X[,Y]) -- X gets 'hh:mm'; optional Y gets 'bss.t'."""
    t = eng.now()
    _store_words(eng, eng.arg_ref(arg_nodes[0], frame), _fmt_time(t))
    if len(arg_nodes) > 1:
        _store_words(eng, eng.arg_ref(arg_nodes[1], frame), _fmt_time2(t))


def b_DATE(eng, frame, arg_nodes):
    """CALL DATE(array) -- today's date as 'dd-mmm-yy', left-justified in 2 words."""
    _store_words(eng, eng.arg_ref(arg_nodes[0], frame), _fmt_date(eng.now()))


def b_EXIT(eng, frame, arg_nodes):
    """CALL EXIT -- return control to the monitor (terminate the program)."""
    raise StopExecution()


def b_ERRSNS(eng, frame, arg_nodes):
    """CALL ERRSNS(I[,J]) -- return the (first[,second]) status code of the last
    I/O operation (V5 App H Table H-1). The second argument is optional."""
    first, second = eng.last_io_error
    eng.arg_ref(arg_nodes[0], frame).write(eng.tgt.wrap(int(first)))
    if len(arg_nodes) > 1:
        eng.arg_ref(arg_nodes[1], frame).write(eng.tgt.wrap(int(second)))


def b_ERRSET(eng, frame, arg_nodes):
    """CALL ERRSET(N) -- suppress arithmetic/library error typeout after N
    occurrences (V5 Table 15-3; default N=2 when never called)."""
    eng.errset_limit = int(eng.eval(arg_nodes[0], frame))


def b_SLITE(eng, frame, arg_nodes):
    """CALL SLITE(I) -- turn console sense light I on (I=0 turns all off)."""
    i = int(eng.eval(arg_nodes[0], frame))
    if i == 0:
        eng.sense_lights.clear()
    elif 1 <= i <= 36:
        eng.sense_lights.add(i)


def b_SLITET(eng, frame, arg_nodes):
    """CALL SLITET(I,J) -- J=1 if light I is on (then turn it off), else J=2."""
    i = int(eng.eval(arg_nodes[0], frame))
    on = i in eng.sense_lights
    eng.sense_lights.discard(i)
    eng.arg_ref(arg_nodes[1], frame).write(1 if on else 2)


def b_SSWTCH(eng, frame, arg_nodes):
    """CALL SSWTCH(I,J) -- J=1 if data switch I is set, else J=2 (no switches here)."""
    eng.arg_ref(arg_nodes[1], frame).write(2)


def b_RELEAS(eng, frame, arg_nodes):
    """CALL RELEAS(unit) -- close out I/O on a device."""
    eng.io.pop(int(eng.eval(arg_nodes[0], frame)), None)


def b_SETRAN(eng, frame, arg_nodes):
    """CALL SETRAN(seed) -- seed the FORTRAN-10 RAN generator (manual Ch15). The
    generator state is an engine service (eng.rng); the driver may also seed it."""
    eng.seed_rng(int(eng.eval(arg_nodes[0], frame)))


def b_RAN(eng, frame, arg_nodes):
    """RAN(x) -- uniform random real in [0,1) (manual Ch15). The argument is a dummy
    in our model; the sequence is reproducible via SETRAN / the injected RNG seed."""
    return eng.rng.random()


def b_SAVRAN(eng, frame, arg_nodes):
    """CALL SAVRAN(I) -- save the last RAN value. RNG-state capture isn't modeled;
    we just return a defined value so the call is harmless."""
    eng.arg_ref(arg_nodes[0], frame).write(0)


def _noop(eng, frame, arg_nodes):
    """A standard-library routine with no effect in this (no-hardware/OS) environment
    -- callable so source that references it still loads and runs."""
    return None


# Calcomp plotter, core dumps, SORT, illegal-char flag, and the FORTRAN-10 realtime
# library (Appendix G): registered as callable no-ops. NUMBER/WHERE/LINE/LEGAL are
# DELIBERATELY omitted -- those names commonly collide with user variables, and a name
# can't be both a variable and a subroutine; a host that needs the plotting NUMBER/
# WHERE/LINE or the LEGAL flag can register them itself.
_NOOP_LIB = (
    "AXIS PLOT PLOTS SCALE SYMBOL MKTBL SETABL DUMP PDUMP SORT ILL "
    "LOCK RTINIT CONECT RTSTRT BLKRW RTREAD RTWRIT STATO STATI RTSLP "
    "RTWAKE DISMIS DISCON UNLOCK GETCOR"
).split()


STDLIB = {
    "TIME": b_TIME,
    "DATE": b_DATE,
    "EXIT": b_EXIT,
    "ERRSNS": b_ERRSNS,
    "ERRSET": b_ERRSET,
    "SLITE": b_SLITE,
    "SLITET": b_SLITET,
    "SSWTCH": b_SSWTCH,
    "RELEAS": b_RELEAS,
    "SAVRAN": b_SAVRAN,
    "RAN": b_RAN,
    "SETRAN": b_SETRAN,
    **{nm: _noop for nm in _NOOP_LIB},
}
