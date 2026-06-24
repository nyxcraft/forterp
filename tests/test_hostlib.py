"""Unit tests for the declarative builtin marshalling layer (forterp.hostlib).

These exercise the mode binding directly against the engine's real reference objects
(CellRef/ArrayView) via a tiny stand-in engine, so they test the marshalling contract
without spinning up the whole interpreter. In this stand-in a "node" IS its value (for
eval) or IS its reference (for arg_ref), which is all the modes touch."""

from forterp.engine import ArrayView, CellRef
from forterp.hostlib import (
    ARRAY,
    FLOAT,
    IN,
    INT,
    OUT,
    STR,
    Monitor,
    OutRef,
    builtins_in,
    fcall,
    make_builtin,
    monitor,
    uuo,
)


class FakeEng:
    """Minimal engine: eval returns the node as its value; arg_ref returns the node as
    its reference. Tests pass literal values for IN-modes and real CellRef/ArrayView for
    OUT/ARRAY-modes."""

    def eval(self, node, frame):
        return node

    def arg_ref(self, node, frame):
        return node


def test_in_modes_pass_values_with_coercion():
    seen = {}

    @fcall("F", args=(IN, INT, FLOAT))
    def f(a, b, c):
        seen.update(a=a, b=b, c=c)
        return 42

    rv = f(FakeEng(), None, ["x", 7.9, 3])
    assert rv == 42  # the body's return value propagates (function-reference dispatch)
    assert seen == {"a": "x", "b": 7, "c": 3.0}  # INT/FLOAT coerce; IN is verbatim


def test_str_mode_resolves_literal_packed_and_plain():
    from forterp import PDP10
    from forterp.ast import StrLit

    class E:  # eval returns the node as its value; STR also needs the target's char codec
        tgt = PDP10

        def eval(self, node, frame):
            return node

    e = E()
    assert STR.bind(e, None, StrLit("EMPIRE.DAT")) == "EMPIRE.DAT"  # quoted literal -> text
    assert STR.bind(e, None, PDP10.pack("HI")) == "HI"  # packed word -> decoded, padding stripped
    assert STR.bind(e, None, "plain") == "plain"  # already a string
    assert STR.bind(e, None, None) is None  # fewer actuals than declared modes


def test_missing_actual_binds_none():
    seen = {}

    @fcall("F", args=(INT, INT))
    def f(a, b):
        seen.update(a=a, b=b)

    f(FakeEng(), None, [5])  # only one actual supplied for two declared modes
    assert seen == {"a": 5, "b": None}


def test_out_writes_through_the_reference():
    store = [10, 20, 30]
    ref = CellRef(store, 1)

    @fcall("SET2", args=(OUT,))
    def set2(x):
        assert x.get() == 20  # reads the current actual
        x.set(99)

    set2(FakeEng(), None, [ref])
    assert store[1] == 99  # the caller's word was mutated by reference


def test_array_mode_reaches_elements_and_backing_store():
    store = [0, 0, 0, 0, 0]
    view = ArrayView(store, 1)  # base offset 1

    @fcall("FILL", args=(ARRAY, INT))
    def fill(arr, n):
        for i in range(n):
            arr.set_at(i, i + 1)
        assert arr.get_at(0) == 1
        assert arr.store is store and arr.base == 1  # block ops can index directly

    fill(FakeEng(), None, [view, 3])
    assert store == [0, 1, 2, 3, 0]


def test_outref_base_falls_back_to_cellref_idx():
    ref = OutRef(CellRef([1, 2, 3], 2))
    assert ref.store == [1, 2, 3]
    assert ref.base == 2  # CellRef exposes .idx, surfaced as .base


def test_raw_passes_engine_frame_and_nodes_through():
    captured = {}

    @fcall("RAWFN", raw=True)
    def rawfn(eng, frame, nodes):
        captured.update(eng=eng, frame=frame, nodes=nodes)
        return "ok"

    eng = FakeEng()
    rv = rawfn(eng, "FRAME", ["n0", "n1"])
    assert rv == "ok"
    assert captured == {"eng": eng, "frame": "FRAME", "nodes": ["n0", "n1"]}


def test_make_builtin_matches_decorator_and_carries_metadata():
    def body(a):
        return a

    wrapped = make_builtin(body, args=(INT,))
    assert wrapped(FakeEng(), None, [4.6]) == 4

    @fcall("NAMED", args=(INT,))
    def named(a):
        return a

    assert named.builtin_name == "NAMED"
    assert named.fcall_fn is not None
    assert named.builtin_aliases == ()  # defaults: no aliases, no origin
    assert named.builtin_origin is None


# ---- alias / origin metadata + discovery ---------------------------------------------------


def test_builtin_alias_and_origin_metadata():
    @fcall("CORR", args=(INT,), alias="ICORR", origin="CURSOR.MAC")
    def corr(x):
        return x

    assert corr.builtin_name == "CORR"
    assert corr.builtin_aliases == ("ICORR",)  # str alias normalized to a 1-tuple
    assert corr.builtin_origin == "CURSOR.MAC"
    assert corr.fcall_fn is not None


def test_builtins_in_registers_name_aliases_and_module_BUILTINS():
    import types

    mod = types.ModuleType("fake_host_module")

    @fcall("CORR", alias=("ICORR", "JCORR"))
    def corr():
        return 0

    mod.CORR = corr
    mod.BUILTINS = {"EXTRA": corr}

    table = builtins_in(mod)
    assert table["CORR"] is corr
    assert table["ICORR"] is corr and table["JCORR"] is corr  # both aliases discovered
    assert table["EXTRA"] is corr  # module-level BUILTINS merged on top


# ---- the baseline Monitor facade ------------------------------------------------------


class FakeHostEng(FakeEng):
    """FakeEng plus the engine host seam the baseline facade reads (emit/getch/readline,
    root/save_root, clock) and the terminal state it now delegates to (column/width/autowrap,
    which live on the engine -- emit() owns the column, set_autowrap the free-CR-LF switch)."""

    def __init__(self, root="."):
        self.out = []
        self.root = root
        self.save_root = root
        self.clock = 1234
        self._col = 0
        self._tty_width = 80
        self._autowrap = True
        self._set_autowrap = None  # optional front-end hook (an ANSI renderer wires it)

    def emit(self, s):
        self.out.append(s)
        nl = s.rfind("\n")  # track the column like Engine.emit (the facade reads eng._col)
        self._col = (len(s) - nl - 1) if nl >= 0 else self._col + len(s)

    def set_autowrap(self, on):
        self._autowrap = bool(on)
        if self._set_autowrap:
            self._set_autowrap(bool(on))

    def getch(self):
        return "Q"

    def readline(self):
        return "hi\n"


def test_baseline_tty_tracks_column():
    eng = FakeHostEng()
    mon = Monitor(eng)
    mon.tty.write("abc")
    assert eng.out == ["abc"] and mon.tty.col == 3
    mon.tty.tab(6)  # advance to absolute column 6
    assert eng.out[-1] == "   " and mon.tty.col == 6
    mon.tty.write("xy\n")  # a newline resets the tracked column
    assert mon.tty.col == 0
    mon.tty.crlf()  # smart newline: already at the margin -> emits nothing
    assert eng.out[-1] == "xy\n"


def test_baseline_tty_echo_defaults_on_and_toggles():
    mon = Monitor(FakeHostEng())  # no set_echo hook -> just records the state
    assert mon.tty.echo is True  # a normal terminal echoes typed input
    mon.tty.echo = False  # e.g. raw single-key input (ECHOFF)
    assert mon.tty.echo is False


def test_baseline_tty_echo_drives_the_set_echo_hook():
    calls = []
    eng = FakeHostEng()
    eng.set_echo = calls.append  # a front-end that owns a real terminal wires this
    mon = Monitor(eng)
    mon.tty.echo = False  # ECHOFF
    mon.tty.echo = True  # ECHOON
    assert calls == [False, True]  # each assignment changed the actual terminal mode
    assert mon.tty.echo is True


def test_baseline_tty_autowrap_defaults_on_and_drives_the_hook():
    calls = []
    eng = FakeHostEng()
    eng._set_autowrap = calls.append  # an ANSI front-end wires this hook (ESC[?7l / ESC[?7h)
    mon = Monitor(eng)
    assert mon.tty.autowrap is True  # terminals wrap at the right margin by default
    mon.tty.autowrap = False  # TRMOP2: set .TONFC (no free CR-LF) for a full-screen display
    assert mon.tty.autowrap is False and calls == [False]


def test_baseline_tty_autowrap_records_without_a_hook():
    mon = Monitor(FakeHostEng())  # no set_autowrap hook -> just records the state
    mon.tty.autowrap = False
    assert mon.tty.autowrap is False


def test_baseline_clock_reads_engine_and_ticks():
    eng = FakeHostEng()
    mon = Monitor(eng)
    assert mon.clock.ms == 1234  # the engine's fixed reading
    assert mon.clock.tick() == 100 and mon.clock.tick() == 200  # monotonic per query


def test_baseline_files_read_under_root(tmp_path):
    (tmp_path / "HELLO.TXT").write_text("hi there")
    eng = FakeHostEng(root=str(tmp_path))
    mon = Monitor(eng)
    assert mon.files.read("HELLO.TXT") == "hi there"
    assert mon.files.read("NOPE.TXT", missing="<none>") == "<none>"  # absent -> the sentinel
    assert mon.files.root_path("X").endswith("X")


def test_host_builds_and_caches_baseline():
    eng = FakeHostEng()
    mon1 = monitor(eng)
    assert isinstance(mon1, Monitor) and mon1.eng is eng
    assert monitor(eng) is mon1  # cached
    assert eng.monitor is mon1  # on the engine's injectable slot


# ---- the @uuo decorator --------------------------------------------------------------------


def test_uuo_injects_baseline_facade_then_engine_frame_nodes():
    captured = {}

    @uuo("OUTSTR")
    def outstr(mon, eng, frame, nodes):  # raw=True default: mon, then (eng, frame, arg_nodes)
        captured.update(mon=mon, eng=eng, frame=frame, nodes=nodes)
        mon.tty.write("hello")
        return 7

    eng = FakeHostEng()
    rv = outstr(eng, "FR", ["n0"])
    assert rv == 7  # return value still propagates (function-reference dispatch)
    assert isinstance(captured["mon"], Monitor)
    assert captured["eng"] is eng and captured["frame"] == "FR" and captured["nodes"] == ["n0"]
    assert eng.out == ["hello"]
    assert eng.monitor is captured["mon"]  # the baseline was cached on the engine


def test_uuo_nonraw_marshals_actuals_after_mon():
    seen = {}

    @uuo("SETIT", args=(INT,), raw=False)
    def setit(mon, n):  # declared modes follow mon
        seen.update(mon=mon, n=n)

    setit(FakeHostEng(), None, [4.9])
    assert isinstance(seen["mon"], Monitor)
    assert seen["n"] == 4  # INT coerces the actual, bound after mon


def test_injected_facade_overrides_baseline():
    class RichMon:
        def __init__(self, eng):
            self.eng = eng
            self.extra = "identity"  # a service the baseline doesn't have

    @uuo("WHOAMI")
    def whoami(mon, eng, frame, nodes):
        return mon.extra

    eng = FakeHostEng()
    eng.monitor = RichMon(eng)  # inject a richer facade before running
    assert whoami(eng, None, []) == "identity"  # @uuo receives the injected one, not baseline
    assert not isinstance(eng.monitor, Monitor)  # baseline never built


def test_host_ppn_maps_gid_uid_and_falls_back_when_oversized(monkeypatch):
    """host_ppn packs [gid,,uid] into an 18-bit-half PPN word, falling back to a safe in-range
    PPN when a modern 32-bit uid/gid won't fit -- rather than silently truncating it."""
    import forterp.hostlib as H

    monkeypatch.setattr(H.os, "getuid", lambda: 1000)
    monkeypatch.setattr(H.os, "getgid", lambda: 1000)
    assert H.host_ppn() == (1000 << 18) | 1000  # normal ids -> [gid,,uid]

    monkeypatch.setattr(H.os, "getuid", lambda: 1_000_000)  # larger than an 18-bit half
    monkeypatch.setattr(H.os, "getgid", lambda: 1_000_000)
    ppn = H.host_ppn()
    assert 0 <= (ppn >> 18) <= 0o777777 and 0 <= (ppn & 0o777777) <= 0o777777  # in range
    assert ppn != (((1_000_000 & 0o777777) << 18) | (1_000_000 & 0o777777))  # not truncated


def test_identity_service_on_the_baseline_facade():
    """The baseline Monitor exposes the host identity (uid/gid/user/ppn), so monitor calls get it
    even in the bare drop-in (no injected facade)."""
    import forterp.hostlib as H

    mon = H.Monitor(FakeHostEng())
    assert mon.identity.ppn == H.host_ppn()
    assert isinstance(mon.identity.user, str)


def test_gettab_recognized_tables_raise_on_unmodeled_and_honor_the_registry():
    """forterp answers the tables it can give a faithful generic value -- .GTPPN(2,-1) -> guest
    [0,0], .GTJTC(0o120,-1) -> 0 (a forterp job is unclassed) -- raises UnmodeledMonitorTable on
    any other table (rather than guessing 0), and lets eng.gettab override per table."""
    import pytest

    from forterp.uuolib import _GUEST_PPN, UnmodeledMonitorTable, b_GETTAB

    eng = FakeHostEng()
    assert b_GETTAB(eng, None, [2, -1]) == _GUEST_PPN  # .GTPPN -> guest [0,0]
    assert b_GETTAB(eng, None, [0o120, -1]) == 0  # .GTJTC -> 0 (no class scheduler)
    with pytest.raises(UnmodeledMonitorTable):  # an unrecognized table -> fail loud, no blind 0
        b_GETTAB(eng, None, [0o161, -1])

    eng.gettab = {2: 1.5}  # a host maps a table it cares about
    assert b_GETTAB(eng, None, [2, -1]) == 1.5  # the registry overrides a recognized default
