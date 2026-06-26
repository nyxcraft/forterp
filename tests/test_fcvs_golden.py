"""Differential validation of forterp's formatted output against gfortran goldens.

`tests/fcvs_golden/<NAME>.out` holds gfortran's stdout (FORTRAN-77 / `-std=legacy`) for each
FCVS routine gfortran compiles and runs to completion, fed the routine's own card deck on stdin
where it has one (regenerate with `python tests/fcvs_golden/regenerate.py` -- needs gfortran).
This is a SECOND, independent oracle layered on top of forterp's own self-check
(test_fcvs_f66_conformance / test_fcvs_f77_conformance): it validates the formatted output
byte-for-byte -- crucially the print-and-eyeball routines that carry no PASS/FAIL self-check.

forterp runs the WHOLE corpus under FORTRAN-77 here -- F77 is valid against all of FCVS, and was
verified to produce output identical to F66 on every F66-valid routine (so the dialect choice
changes no result). The F66 subset is additionally exercised under F66 by test_fcvs_f66_conformance.
forterp runs under carriage_control=False (file output), so, like gfortran writing to a file, it
emits raw records with the ASA control character kept as data in column 1; the compare drops that
one control column and trailing whitespace and matches line-for-line, blank lines / page breaks
INCLUDED. gfortran likewise ran the whole corpus under one permissive mode (-std=legacy).

Each routine is validated by exactly one metric (see _CHECKERS): a byte-match against the golden
(the default, the vast majority), a value-token compare for processor-dependent list-directed
output, or its own self-check where gfortran is an unreliable oracle. The remainder -- where
forterp's output legitimately or knowingly differs from gfortran -- is enumerated and annotated:

  * GFORTRAN_UNRELIABLE -- gfortran is WRONG (or refuses to run sanely); forterp is correct.
    Validated by its self-check instead of the golden.
  * KNOWN_GF_DIFF -- forterp's formatted output differs from gfortran for a documented reason
    that is NOT a self-check failure (a print-and-eyeball FORMAT-edge, or a completeness gap):
    forterp reports no wrong PASS/FAIL, but its bytes are not gfortran's. The tests pin this set,
    so a fix (it starts matching) or a new, unexplained divergence both surface.
  * GF_CANNOT_RUN -- gfortran itself crashes at runtime even with the deck, so there is no golden;
    these are covered by forterp's self-check alone.
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

# gfortran is an UNRELIABLE oracle for these -- forterp's output is correct (or more correct), so
# they are validated by the self-check inspection metric (_self_check_ok), not a byte-match.
GFORTRAN_UNRELIABLE = {
    "FM406": "gfortran computes -0.0 where the test wants 0.0 and so FAILs its OWN test 3; "
    "forterp produces 0.0 and PASSES. Matching would mean reproducing gfortran's -0.0 quirk.",
    "FM257": "PAUSE: in batch gfortran blocks / writes PAUSE to stderr, so the golden is only "
    "the header. forterp prints the PAUSE message to the terminal and runs every test (all PASS).",
}

# forterp's formatted output is NOT byte-equal to gfortran's, for a documented reason that is NOT
# a self-check failure: forterp reports no wrong PASS/FAIL (the F77/F66 conformance baselines stay
# clean), but its bytes differ. All are eyeball-only FORMAT-edge cases or completeness gaps -- the
# honest "ours is different and here is why it's not a wrong answer." A real forterp limitation
# worth a future fix, not a divergence we claim is correct.
KNOWN_GF_DIFF = {
    "FM111": "IOFMTS print-and-eyeball FORMAT audit: forterp's COMPUTED rows differ on some "
    "edit-descriptor edges (FORMAT reversion over a long io-list). Eyeball-only; no self-check.",
    "FM404": "AFMTS print-and-eyeball A/Hollerith-FORMAT audit: forterp's repeated A/H output "
    "stops short of gfortran's on some repeat-count fields. Eyeball-only; no self-check.",
    "FM901": "AFMTF print-and-eyeball A-FORMAT-of-CHARACTER audit: forterp wraps a CHARACTER value "
    "onto the next record where gfortran keeps it inline. Eyeball-only; the tests are INSPECT.",
    "FM903": "IOFMTF print-and-eyeball FORMAT audit: forterp fills a trailing numeric field (0/+0) "
    "that gfortran leaves blank (an edit-descriptor / io-list-exhaustion edge). Eyeball-only.",
}

# gfortran itself crashes at runtime on these (even fed the card deck), so there is NO golden to
# diff against -- they rely on forterp's self-check alone (the conformance baselines run them).
GF_CANNOT_RUN = {
    "FM110": "gfortran aborts at runtime (backtrace, no usable stdout) even with the card deck.",
    "FM403": "gfortran aborts at runtime (backtrace, no usable stdout) even with the card deck.",
    "FM900": "gfortran aborts at runtime (backtrace, no usable stdout) even with the card deck.",
}


def _norm(text):
    # Both sides emit RAW records (forterp under carriage_control=False, like gfortran's file
    # output): the ASA control column is data in column 1. Drop that one control column and
    # trailing whitespace, then compare line-for-line -- blank lines and form-feeds INCLUDED.
    return [(ln[1:] if ln else ln).rstrip() for ln in text.splitlines()]


def _forterp_output(name):
    # The whole corpus runs under F77 -- F77 is valid against all of FCVS (verified output-identical
    # to F66 on every F66-valid routine). gfortran matched it with one permissive -std=legacy run.
    dialect = forterp.F77
    path = os.path.join(CORPUS, f"{name}.FOR")
    stmts = expand_includes(scan_file(path, dialect=dialect).statements, os.path.dirname(path))
    units = parse_units(stmts, on_error=lambda s, m: None, dialect=dialect)
    buf = []
    main = next((u.name for u in units if u.kind == "program"), None)
    try:
        eng = Engine(
            {u.name: u for u in units},
            emit=buf.append,
            readline=lambda: "",
            printer=buf.append,
            target=forterp.NATIVE,
            character_type=dialect.character_type,
            zero_trip_do=dialect.zero_trip_do,
            blank_null=dialect.blank_null,
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


# Inspection metric for a GFORTRAN_UNRELIABLE routine: rather than byte-match gfortran, validate
# forterp by the routine's OWN self-check -- it passes iff it reports at least one PASS and ZERO
# FAILs, across both the per-test result lines ("nnn  PASS/FAIL") and any "nnn TESTS FAILED"
# summary. FCVS routines are self-checking by design, so a clean PASS tally is a true signal even
# where gfortran's transcript is wrong or truncated.
_TEST_RESULT = re.compile(r"^\s*\d+\s+(PASS|FAIL)\b")
_TESTS_FAILED = re.compile(r"(\d+)\s+TESTS?\s+FAILED")


def _self_check_ok(name):
    lines = _norm(_forterp_output(name))
    results = [m.group(1) for ln in lines if (m := _TEST_RESULT.match(ln))]
    summary_fails = [int(m.group(1)) for ln in lines if (m := _TESTS_FAILED.search(ln))]
    return "PASS" in results and "FAIL" not in results and not any(summary_fails)


# Per-routine validation metric. Byte-for-byte against the golden is the default (no masking) for
# the vast majority; a routine whose output is genuinely processor-dependent (list-directed WRITE,
# whose field widths / real precision the standard does NOT fix) opts into a value-token compare;
# a GFORTRAN_UNRELIABLE routine opts into the self-check inspection metric.
_CHECKERS = {
    "FM905": _value_match,
    "FM907": _value_match,
    "FM257": _self_check_ok,  # gfortran blocks at PAUSE -> validate by FM257's own self-check
    "FM406": _self_check_ok,  # gfortran fails its own -0.0 test -> validate by FM406's self-check
}


def _byte_matches(name):
    with open(os.path.join(GOLD, f"{name}.out")) as f:
        return _norm(_forterp_output(name)) == _norm(f.read())


def _matches(name):
    check = _CHECKERS.get(name)
    return check(name) if check is not None else _byte_matches(name)


GOLDENS = sorted(os.path.basename(p)[:-4] for p in glob.glob(os.path.join(GOLD, "FM*.out")))
MATCHING = {n for n in GOLDENS if n not in KNOWN_GF_DIFF and _matches(n)}


def test_goldens_present():
    # gfortran compiles and runs 189 of the 192-routine corpus (the 3 GF_CANNOT_RUN have no golden).
    assert len(GOLDENS) == 189
    assert not (set(GF_CANNOT_RUN) & set(GOLDENS))  # the crashers really have no golden


def test_every_runnable_routine_is_validated():
    # Every routine with a golden is validated by SOME metric -- byte-match, value-token, or
    # self-check -- EXCEPT the enumerated, annotated KNOWN_GF_DIFF. Nothing is silently unchecked:
    # a routine that stops being validated and is not a documented difference fails here.
    unvalidated = sorted(n for n in GOLDENS if n not in KNOWN_GF_DIFF and n not in MATCHING)
    assert not unvalidated, f"no longer validated vs gfortran (not in KNOWN_GF_DIFF): {unvalidated}"


def test_known_gf_diff_really_differ():
    # Keep the documented-difference list honest: each KNOWN_GF_DIFF routine HAS a golden and its
    # bytes really differ from it. If one starts byte-matching (a fix landed), this flags it so the
    # entry -- and its annotation -- is removed, ratcheting the list down.
    assert set(KNOWN_GF_DIFF) <= set(GOLDENS), "a KNOWN_GF_DIFF routine has no golden"
    spurious = sorted(n for n in KNOWN_GF_DIFF if _byte_matches(n))
    assert not spurious, f"these now match gfortran -- drop from KNOWN_GF_DIFF: {spurious}"


def test_gfortran_unreliable_routines_pass_self_check_but_not_the_golden():
    # The gfortran-unreliable routines are validated by their self-check, NOT the golden. Assert
    # both halves: each PASSES its self-check, AND its raw output still differs from the golden --
    # so the alternate metric is warranted, not masking a real match. If one starts byte-matching
    # (goldens regenerated with a fixed gfortran), retire it from GFORTRAN_UNRELIABLE.
    for name in sorted(GFORTRAN_UNRELIABLE):
        assert _self_check_ok(name), f"{name}: self-check no longer passes"
        assert not _byte_matches(name), f"{name} byte-matches gfortran now -- retire from the set"


def test_whole_corpus_is_accounted_for():
    # Every one of the 192 routines is in exactly one bucket: validated against the golden, a
    # documented forterp difference, or a gfortran-cannot-run (no golden) -- none unaccounted.
    corpus = {os.path.basename(p)[:-4] for p in glob.glob(os.path.join(CORPUS, "FM*.FOR"))}
    assert len(corpus) == 192
    accounted = MATCHING | set(KNOWN_GF_DIFF) | set(GF_CANNOT_RUN)
    assert corpus == accounted, f"unaccounted routines: {sorted(corpus - accounted)}"
    assert len(MATCHING) == 185  # 181 byte + FM905/907 value-token + FM257/406 self-check
