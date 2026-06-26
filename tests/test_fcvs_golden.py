"""Differential validation of forterp's formatted output against gfortran goldens.

tests/fcvs_golden/<NAME>.out holds gfortran's stdout for each FCVS-77 routine gfortran runs
to completion (regenerate with `python tests/fcvs_golden/regenerate.py` -- needs gfortran).
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
import re

from fcvs_runner import _card_deck

import forterp
from forterp.engine import Engine, Frame, StopExecution
from forterp.parser import parse_units
from forterp.runtime import install_runtime
from forterp.source import expand_includes, scan_file

GOLD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fcvs_golden")
CORPUS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fcvs")

# The forterp-bug output punch-list -- now EMPTY: every FCVS-77 routine gfortran completes either
# matches forterp's output exactly (129/131) or is a documented gfortran-unreliable divergence
# (FM257/FM406, below). Keep the set so a future regression has a home: a routine whose output
# breaks vs gfortran goes here with a note, and test_expected_outputs_match_gfortran flags it.
#
# Cleared along the way: the COMPLEX cluster (FM503/700/722/809/811/813/815/817/820/828-834/908)
# via a two-word storage-associated COMPLEX scalar (ComplexPairRef); FM715 (CHARACTER functions)
# via the CHARACTER*len FUNCTION header + ret_type-typed result var + a CHARACTER PARAMETER staying
# a str; FM509 (CHARACTER sequence association) via a char-stream view of a CHARACTER array dummy
# over a substring actual (CharSeqView); FM909 via a COMPLEX internal WRITE expanding to two reals,
# the Gw.dEe trailing-blank count, and nX advancing (not blanking); FM915/FM905/FM907/FM910 earlier.
KNOWN_DIVERGENT = set()

# Output differs from the gfortran golden NOT because of a forterp bug, but because gfortran is an
# unreliable oracle for that routine -- forterp's output is correct (or more correct). These are
# validated by the self-check inspection metric (_self_check_ok / _CHECKERS below) instead of a
# byte-match: each is a self-checking FCVS routine, so its own PASS tally is the true signal.
GFORTRAN_UNRELIABLE = {
    "FM406": "gfortran computes -0.0 where the test wants 0.0 and so FAILs its OWN test 3; "
    "forterp produces 0.0 and PASSES. Matching would mean reproducing gfortran's -0.0 quirk.",
    "FM257": "PAUSE: in batch gfortran blocks / writes PAUSE to stderr, so the golden is only "
    "the header. forterp prints the PAUSE message to the terminal and runs every test (all PASS).",
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


# Inspection metric for a routine whose gfortran golden is an unreliable oracle (GFORTRAN_UNRELIABLE
# below): rather than byte-match gfortran, validate forterp by the routine's OWN self-check. It
# passes iff it reports at least one PASS and ZERO FAILs -- across both the per-test result lines
# ("nnn  PASS/FAIL") and any "nnn TESTS FAILED" summary. (Applied only to the curated set below,
# each verified to run its tests; FCVS routines are self-checking by design, so a clean PASS tally
# is a true pass/fail signal even where gfortran's transcript is wrong or truncated.)
_TEST_RESULT = re.compile(r"^\s*\d+\s+(PASS|FAIL)\b")
_TESTS_FAILED = re.compile(r"(\d+)\s+TESTS?\s+FAILED")


def _self_check_ok(name):
    lines = _norm(_forterp_output(name))
    results = [m.group(1) for ln in lines if (m := _TEST_RESULT.match(ln))]
    summary_fails = [int(m.group(1)) for ln in lines if (m := _TESTS_FAILED.search(ln))]
    return "PASS" in results and "FAIL" not in results and not any(summary_fails)


# Per-routine output checkers. Exact (byte-for-byte, see _norm) is the default and stays that
# way for almost every routine -- no masking. A routine whose output is genuinely
# processor-dependent (list-directed WRITE, whose field widths / real precision the standard does
# NOT fix) opts into a tailored value comparison; one whose gfortran golden is unreliable opts
# into the self-check inspection metric instead.
_CHECKERS = {
    "FM905": _value_match,
    "FM907": _value_match,
    "FM257": _self_check_ok,  # gfortran blocks at PAUSE -> validate by FM257's own self-check
    "FM406": _self_check_ok,  # gfortran fails its own -0.0 test -> validate by FM406's self-check
}


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


def test_every_routine_is_validated():
    # Every routine gfortran completes is validated by SOME metric: byte-for-byte against the
    # golden (the default), value tokens for processor-dependent list-directed output (FM905/907),
    # or its own self-check where gfortran is an unreliable oracle (GFORTRAN_UNRELIABLE). Nothing
    # is silently unchecked -- a routine that stops being validated must be on the bug punch-list.
    unvalidated = sorted(n for n in GOLDENS if n not in KNOWN_DIVERGENT and n not in MATCHING)
    assert not unvalidated, f"no longer validated vs gfortran: {unvalidated}"


def test_punchlist_has_no_stale_entries():
    # A routine that now matches must be removed from KNOWN_DIVERGENT -- keeps it honest.
    fixed = sorted(n for n in KNOWN_DIVERGENT if n in MATCHING)
    assert not fixed, f"these now match gfortran -- drop from KNOWN_DIVERGENT: {fixed}"


def test_gfortran_unreliable_routines_pass_self_check_but_not_the_golden():
    # The gfortran-unreliable routines are validated by their self-check, NOT the golden. Assert
    # both halves of that classification hold: each PASSES its self-check, AND its raw output still
    # differs from gfortran's golden -- so the alternate metric is warranted, not masking a real
    # match. If one starts byte-matching (e.g. goldens regenerated with a fixed gfortran), retire
    # it from GFORTRAN_UNRELIABLE so it is validated the normal way.
    for name in sorted(GFORTRAN_UNRELIABLE):
        assert _self_check_ok(name), f"{name}: self-check no longer passes"
        with open(os.path.join(GOLD, f"{name}.out")) as f:
            byte_matches = _norm(_forterp_output(name)) == _norm(f.read())
        assert not byte_matches, f"{name} byte-matches gfortran now -- retire it from the set"


def test_whole_corpus_is_validated():
    # Floor on validated coverage. Now every routine gfortran completes is validated (129 by the
    # golden incl. the two value-token routines, plus FM257/FM406 by self-check) -- the full 131.
    assert len(MATCHING) == len(GOLDENS) == 131
