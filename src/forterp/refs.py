"""Storage references and the faithful memory model for the forterp engine.

Out-of-bounds access follows FORTRAN-10's unchecked-pointer semantics (an OOB or
negative index reads 0, a write is dropped), with optional log/raise modes for the
bounds checker. The Ref/View classes are the single-word and array lvalue handles the
engine builds over COMMON/EQUIVALENCE storage, local cells, substrings, passed
procedures, and word-addressable (punned) memory; linidx/array_size are the
column-major index helpers."""

from __future__ import annotations

from forterp.forbin import dec10_pair_to_double, double_to_dec10_pair

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


class IllegalRecursion(RuntimeError):
    """A subprogram referenced itself, directly or indirectly, while a prior activation was
    still in progress. ANSI X3.9-1978 §15.5.2 prohibits this ("A subprogram must not reference
    itself, either directly or indirectly"); forterp's static local storage cannot represent it
    correctly, so it is rejected rather than silently corrupted. Enable `allow_recursion` (the
    `recursion` dialect knob) to permit it with per-activation local storage instead."""


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


# word_memory codec types whose zero value is complex (read of an OOB datum yields it).
_WMEM_COMPLEX = ("COMPLEX", "DOUBLE COMPLEX")


def wmem_read(wmem, store, off, typ):
    """Read a typed datum from word-addressable (word_memory) storage with the same
    unchecked-pointer semantics as `oob_read`: a datum whose whole span (off .. off+units)
    falls outside the store reads 0 -- 0j for a complex type -- rather than the codec
    faulting with an IndexError. Every word_memory access routes through here so punned
    storage honors the faithful OOB behavior (and the census counters) just like a CellRef."""
    if 0 <= off and off + wmem.units(typ) <= len(store):
        return wmem.read(store, off, typ)
    global OOB_READS
    OOB_READS += 1
    if OOB_CHECK != "off":
        _oob_event(off, len(store), "read")
    return 0j if typ in _WMEM_COMPLEX else 0


def wmem_write(wmem, store, off, typ, v):
    """Write a typed datum to word-addressable (word_memory) storage with the same
    unchecked-pointer semantics as `oob_write`: a datum whose span falls outside the store is
    dropped rather than faulting. The write counterpart of `wmem_read`."""
    if 0 <= off and off + wmem.units(typ) <= len(store):
        wmem.write(store, off, typ, v)
        return
    global OOB_WRITES
    OOB_WRITES += 1
    if OOB_CHECK != "off":
        _oob_event(off, len(store), "write")


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


class ComplexPairRef:
    """A COMPLEX scalar that shares word-addressable storage (COMMON / EQUIVALENCE) occupies
    TWO consecutive word-cells -- real part, then imaginary (X3.9-1978 Table 1 / 8.3 storage
    association). So a REAL EQUIVALENCEd onto those words (the FCVS `EQUIVALENCE(CVAL, R2(2))`
    idiom) reads each clean float, instead of finding one cell holding a Python complex object.

    A COMPLEX decomposes losslessly into two REALs -- unlike DOUBLE PRECISION (one value smeared
    bit-wise across two words), which forterp does not split. Non-associated COMPLEX (a local
    scalar) stays a single complex cell; only storage association needs this pair."""

    __slots__ = ("store", "idx")

    def __init__(self, store, idx):
        self.store, self.idx = store, idx

    def read(self):
        re = oob_read(self.store, self.idx)
        im = oob_read(self.store, self.idx + 1)
        return complex(float(re), float(im))

    def write(self, v):
        v = v if isinstance(v, complex) else complex(float(v), 0.0)
        oob_write(self.store, self.idx, v.real)
        oob_write(self.store, self.idx + 1, v.imag)


class DecDoublePairRef:
    """A DOUBLE PRECISION scalar in word-addressable storage on a packed-double target (PDP10),
    held as the two genuine 36-bit machine words of the KL10 doubleword (high, low). Reading
    reassembles the host float; writing splits it (forbin codec). So an INTEGER EQUIVALENCEd onto
    the two words reads the real machine words, exactly as FORTRAN-10 does -- unlike the NATIVE
    target, where a DOUBLE is one host float in the first cell with a zero shadow in the second.

    The DEC-10 doubleword carries more mantissa bits than a host double, so float -> pair -> float
    round-trips losslessly; only the reinterpretation idiom (reading the halves) differs."""

    __slots__ = ("store", "idx")

    def __init__(self, store, idx):
        self.store, self.idx = store, idx

    def read(self):
        hi = int(oob_read(self.store, self.idx))
        lo = int(oob_read(self.store, self.idx + 1))
        return dec10_pair_to_double(hi, lo)

    def write(self, v):
        hi, lo = double_to_dec10_pair(float(v))
        oob_write(self.store, self.idx, hi)
        oob_write(self.store, self.idx + 1, lo)


class DoubleComplexPairRef:
    """A DOUBLE COMPLEX scalar in word-addressable storage (COMMON / EQUIVALENCE), occupying the
    standard FOUR storage units: the real DOUBLE in cells (idx, idx+1) and the imaginary DOUBLE in
    (idx+2, idx+3), each laid out exactly as a lone DOUBLE PRECISION is on this target. On a
    packed-double target (PDP10) each half is its two genuine KL10 machine words (forbin codec);
    otherwise each half is one host float in the leading cell with a zero shadow in the trailing
    one -- so a REAL/DOUBLE overlay onto cell idx reads the real part and onto cell idx+2 the
    imaginary part, the DOUBLE analogue of how ComplexPairRef splits a single COMPLEX."""

    __slots__ = ("store", "idx", "packed")

    def __init__(self, store, idx, packed):
        self.store, self.idx, self.packed = store, idx, packed

    def read(self):
        i = self.idx
        if self.packed:
            re = dec10_pair_to_double(
                int(oob_read(self.store, i)), int(oob_read(self.store, i + 1))
            )
            im = dec10_pair_to_double(
                int(oob_read(self.store, i + 2)), int(oob_read(self.store, i + 3))
            )
        else:
            re = float(oob_read(self.store, i))
            im = float(oob_read(self.store, i + 2))
        return complex(re, im)

    def write(self, v):
        v = v if isinstance(v, complex) else complex(float(v), 0.0)
        i = self.idx
        if self.packed:
            hi, lo = double_to_dec10_pair(v.real)
            oob_write(self.store, i, hi)
            oob_write(self.store, i + 1, lo)
            hi, lo = double_to_dec10_pair(v.imag)
            oob_write(self.store, i + 2, hi)
            oob_write(self.store, i + 3, lo)
        else:
            oob_write(self.store, i, v.real)
            oob_write(self.store, i + 1, 0)
            oob_write(self.store, i + 2, v.imag)
            oob_write(self.store, i + 3, 0)


class DictRef:
    """Reference to a named local scalar (lazily defaulting to 0)."""

    __slots__ = ("d", "key")

    def __init__(self, d, key):
        self.d, self.key = d, key

    def read(self):
        return self.d.get(self.key, 0)

    def write(self, v):
        self.d[self.key] = v


class WordRef:
    """Writable reference to a storage-associated scalar in word-addressable memory: read/write go
    through the target's typed codec (wordmem), so the bits are reinterpreted by the access type.
    Used when `word_memory` is on (PDP10) in place of a CellRef/ComplexPairRef/DecDoublePairRef."""

    __slots__ = ("wmem", "store", "off", "typ")

    def __init__(self, wmem, store, off, typ):
        self.wmem, self.store, self.off, self.typ = wmem, store, off, typ

    def read(self):
        return wmem_read(self.wmem, self.store, self.off, self.typ)

    def write(self, v):
        wmem_write(self.wmem, self.store, self.off, self.typ, v)


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


class WordArrayView:
    """An array view over word-addressable storage (word_memory): element i lives at
    base + i*units words and .loc(i) yields a WordRef that reads/writes through the typed codec,
    so an array element puns faithfully (a REAL element read as INTEGER is its machine word)."""

    __slots__ = ("wmem", "store", "base", "typ", "units")

    def __init__(self, wmem, store, base, typ):
        self.wmem, self.store, self.base, self.typ = wmem, store, base, typ
        self.units = wmem.units(typ)

    def loc(self, i):
        return WordRef(self.wmem, self.store, self.base + i * self.units, self.typ)


class CharSeqElemRef:
    """One element of a CHARACTER array dummy that is sequence-associated with a CHARACTER actual
    (a substring or array element): a `width`-char window into the actual's character storage,
    read/written as a contiguous stream that SPANS the underlying array cells (each `cell_len`
    chars). `start` is the window's char offset measured from cell `cell0`."""

    __slots__ = ("store", "cell0", "start", "cell_len", "width")

    def __init__(self, store, cell0, start, cell_len, width):
        self.store, self.cell0, self.start = store, cell0, start
        self.cell_len, self.width = cell_len, width

    def _cell(self, off):  # (cell index, char position) of stream offset `off`
        return self.cell0 + off // self.cell_len, off % self.cell_len

    def read(self):
        out = []
        for k in range(self.width):
            c, p = self._cell(self.start + k)
            s = oob_read(self.store, c)
            s = s.ljust(self.cell_len) if isinstance(s, str) else " " * self.cell_len
            out.append(s[p])
        return "".join(out)

    def write(self, v):
        v = str(v)[: self.width].ljust(self.width)
        for k, ch in enumerate(v):
            c, p = self._cell(self.start + k)
            s = oob_read(self.store, c)
            s = s.ljust(self.cell_len) if isinstance(s, str) else " " * self.cell_len
            oob_write(self.store, c, s[:p] + ch + s[p + 1 :])


class CharSeqView:
    """A CHARACTER array dummy sequence-associated with a CHARACTER actual that is a substring or
    array element (X3.9-1978 17.x): the dummy's `elem_len`-char elements tile the actual's
    character storage as one contiguous stream. loc(i) is element i's window in that stream,
    spanning the underlying array cells as needed."""

    __slots__ = ("store", "cell0", "char0", "cell_len", "elem_len")

    def __init__(self, store, cell0, char0, cell_len, elem_len):
        self.store, self.cell0, self.char0 = store, cell0, char0
        self.cell_len, self.elem_len = cell_len, elem_len

    def loc(self, i):
        return CharSeqElemRef(
            self.store, self.cell0, self.char0 + i * self.elem_len, self.cell_len, self.elem_len
        )


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
