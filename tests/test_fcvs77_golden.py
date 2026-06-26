"""Differential validation of forterp's formatted output against gfortran goldens.

tests/fcvs77_golden/<NAME>.out holds gfortran's stdout for each FCVS-77 routine gfortran runs
to completion (regenerate with `python tests/fcvs77_golden/regenerate.py` -- needs gfortran).
This validates forterp's formatted output -- crucially the print-and-eyeball routines that
carry no self-check -- WITHOUT gfortran at test time.

forterp runs under carriage_control=False (file output), so -- like gfortran writing to a file
-- it emits raw records with the ASA control character kept as data in column 1, rather than
interpreting it as a printer (forterp's default). Both sides are then raw, so the compare just
drops that one control column and trailing whitespace and matches line-for-line, blank lines
and page breaks INCLUDED (no normalisation that could mask a spurious blank-line / break diff).

KNOWN_DIVERGENT is the output-conformance punch-list: routines whose output does not yet match
gfortran (early termination on an unsupported feature, or a value/format bug). The tests assert
(a) every other golden matches exactly and (b) the punch-list has no stale entries -- so fixing
a routine forces removing its name here, keeping the list honest.
"""

import glob
import os

from fcvs_runner import _card_deck

import forterp
from forterp.engine import Engine, Frame, StopExecution
from forterp.parser import parse_units
from forterp.runtime import install_runtime
from forterp.source import expand_includes, scan_file

GOLD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fcvs77_golden")
CORPUS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fcvs77")

# Output does not yet match gfortran -- the punch-list. Shrinks as bugs are fixed.
KNOWN_DIVERGENT = {
    "FM257",
    "FM406",
    "FM503",
    "FM509",
    "FM700",
    "FM715",
    "FM722",
    "FM809",
    "FM811",
    "FM813",
    "FM815",
    "FM817",
    "FM820",
    "FM828",
    "FM829",
    "FM830",
    "FM831",
    "FM833",
    "FM834",
    # FM915 fixed -- INQUIRE ACCESS/FORM specifiers now match gfortran.
    # FM905 / FM907 fixed -- list-directed output is now FORTRAN-shaped (T/F logicals, CHARACTER
    # text, char-after-char concatenation) and validated by the per-test _value_match checker.
    "FM908",
    "FM909",
    # FM910 fixed -- unformatted COMPLEX round-trips through the JSON record store, and the
    # multi-record CHARACTER-ARRAY internal READ advances records on '/'.
}


def _norm(text):
    # Both sides now emit RAW records (forterp under carriage_control=False, like gfortran's
    # file output): the ASA control column is data in column 1. Drop that one control column
    # and trailing whitespace, then compare line-for-line -- blank lines and form-feeds INCLUDED
    # (the old normaliser dropped them, which masked spurious blank-line / page-break diffs).
    return [(ln[1:] if ln else ln).rstrip() for ln in text.splitlines()]


def _forterp_output(name):
    path = os.path.join(CORPUS, f"{name}.FOR")
    stmts = expand_includes(scan_file(path, dialect=forterp.F77).statements, os.path.dirname(path))
    units = parse_units(stmts, on_error=lambda s, m: None, dialect=forterp.F77)
    buf = []
    main = next((u.name for u in units if u.kind == "program"), None)
    try:
        # Use the SAME engine configuration as the conformance harness (fcvs_runner): the full
        # F77 dialect flags and the routine's own embedded card deck. Running F77 routines with
        # only character_type (not zero_trip_do / blank_null) and no input deck gave some
        # routines wrong output, diverging from gfortran for harness reasons, not real ones.
        eng = Engine(
            {u.name: u for u in units},
            emit=buf.append,
            readline=lambda: "",
            printer=buf.append,
            target=forterp.NATIVE,
            character_type=True,
            zero_trip_do=forterp.F77.zero_trip_do,
            blank_null=forterp.F77.blank_null,
            carriage_control=False,  # file output (raw ASA column), to compare with gfortran
        )
        install_runtime(eng)
        eng.io[5] = {"lines": _card_deck(path), "pos": 0, "mode": "r", "text": True}
        eng.max_steps = 50_000_000
        eng.run(Frame(eng.rts[main], {}))
    except (StopExecution, Exception):
        pass
    return "".join(buf)


def _num(tok):
    """Parse a FORTRAN numeric token -> float, else None. D and E exponents are equivalent."""
    try:
        return float(tok.replace("D", "E").replace("d", "e"))
    except ValueError:
        return None


def _value_seq(text):
    """Flatten the output to a token sequence -- numbers as floats, everything else as text --
    splitting on whitespace and on ( ) , so complex literals and comma-lists become their numeric
    parts. Discards line structure, field widths, and numeric precision/exponent style, which are
    PROCESSOR-DEPENDENT for list-directed output (X3.9-1978 13.6); the VALUES must still match."""
    seq = []
    for ln in _norm(text):
        for tok in ln.replace("(", " ").replace(")", " ").replace(",", " ").split():
            n = _num(tok)
            seq.append(("n", n) if n is not None else ("s", tok))
    return seq


def _value_match(name):
    """Lenient per-test checker: the same VALUES and text tokens in order, tolerating
    list-directed field width / precision / exponent style / record wrapping."""
    with open(os.path.join(GOLD, f"{name}.out")) as f:
        gold = _value_seq(f.read())
    ours = _value_seq(_forterp_output(name))
    if len(gold) != len(ours):
        return False
    for (kg, g), (ko, o) in zip(gold, ours):
        if kg != ko:
            return False
        if kg == "n":
            if abs(g - o) > 1e-6 * max(1.0, abs(g), abs(o)):
                return False
        elif g != o:
            return False
    return True


# Per-routine output checkers. Exact (byte-for-byte, see _norm) is the default and stays that
# way for almost every routine -- no masking. A routine whose output is genuinely
# processor-dependent (list-directed WRITE, whose field widths / real precision the standard does
# NOT fix) opts into a tailored, as-exact-as-possible value comparison instead.
_CHECKERS = {"FM905": _value_match, "FM907": _value_match}


def _matches(name):
    check = _CHECKERS.get(name)
    if check is not None:
        return check(name)
    with open(os.path.join(GOLD, f"{name}.out")) as f:
        gold = _norm(f.read())
    return _norm(_forterp_output(name)) == gold


GOLDENS = sorted(os.path.basename(p)[:-4] for p in glob.glob(os.path.join(GOLD, "FM*.out")))
MATCHING = {n for n in GOLDENS if _matches(n)}


def test_goldens_present():
    # gfortran completes 131 of the 140 routines on empty input (9 need FCVS control cards).
    assert len(GOLDENS) == 131


def test_expected_outputs_match_gfortran():
    # Every routine not on the punch-list reproduces gfortran's output exactly.
    regressed = sorted(n for n in GOLDENS if n not in KNOWN_DIVERGENT and n not in MATCHING)
    assert not regressed, f"output regressed vs gfortran golden: {regressed}"


def test_punchlist_has_no_stale_entries():
    # A routine that now matches must be removed from KNOWN_DIVERGENT -- keeps it honest.
    fixed = sorted(n for n in KNOWN_DIVERGENT if n in MATCHING)
    assert not fixed, f"these now match gfortran -- drop from KNOWN_DIVERGENT: {fixed}"


def test_most_of_the_corpus_matches():
    # Floor on validated output coverage (ratchets up as the punch-list shrinks).
    assert len(MATCHING) >= 110
