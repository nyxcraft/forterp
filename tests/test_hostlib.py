"""Unit tests for the declarative builtin marshalling layer (forterp.hostlib).

These exercise the mode binding directly against the engine's real reference objects
(CellRef/ArrayView) via a tiny stand-in engine, so they test the marshalling contract
without spinning up the whole interpreter. In this stand-in a "node" IS its value (for
eval) or IS its reference (for arg_ref), which is all the modes touch."""

from forterp.engine import ArrayView, CellRef
from forterp.hostlib import ARRAY, FLOAT, IN, INT, OUT, OutRef, builtin, make_builtin


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

    @builtin("F", args=(IN, INT, FLOAT))
    def f(a, b, c):
        seen.update(a=a, b=b, c=c)
        return 42

    rv = f(FakeEng(), None, ["x", 7.9, 3])
    assert rv == 42  # the body's return value propagates (function-reference dispatch)
    assert seen == {"a": "x", "b": 7, "c": 3.0}  # INT/FLOAT coerce; IN is verbatim


def test_missing_actual_binds_none():
    seen = {}

    @builtin("F", args=(INT, INT))
    def f(a, b):
        seen.update(a=a, b=b)

    f(FakeEng(), None, [5])  # only one actual supplied for two declared modes
    assert seen == {"a": 5, "b": None}


def test_out_writes_through_the_reference():
    store = [10, 20, 30]
    ref = CellRef(store, 1)

    @builtin("SET2", args=(OUT,))
    def set2(x):
        assert x.get() == 20  # reads the current actual
        x.set(99)

    set2(FakeEng(), None, [ref])
    assert store[1] == 99  # the caller's word was mutated by reference


def test_array_mode_reaches_elements_and_backing_store():
    store = [0, 0, 0, 0, 0]
    view = ArrayView(store, 1)  # base offset 1

    @builtin("FILL", args=(ARRAY, INT))
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

    @builtin("RAWFN", raw=True)
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

    @builtin("NAMED", args=(INT,))
    def named(a):
        return a

    assert named.builtin_name == "NAMED"
    assert named.fcall_fn is not None
