"""Run the vendored FCVS conformance corpus (tests/fcvs/) through the interpreter.

FCVS audit routines are self-checking: each computes a value, compares it to the
known-correct value via an arithmetic IF, tallies PASS/FAIL/DELETE counts, and
prints a run summary ("nnn TESTS PASSED", "nnn ERRORS ENCOUNTERED") to the line
printer (unit 6). We capture that printer listing (engine.printer sink) and parse
the summary -- the report IS line-printer output, not terminal I/O, so it is read
from a dedicated buffer, separate from any terminal stream.

FCVS is ONE corpus (192 routines) -- tests/fcvs/. It is NOT split by dialect; the dialect just
determines how much of it is valid: FORTRAN-66 is valid against the F66_SUBSET (the routines that
predate the F77 CHARACTER type etc.), while FORTRAN-77 is valid against ALL of it. So the F66
driver runs `run_corpus(files=F66_SUBSET)` and the F77 driver runs the whole directory. Within a
run, every selected file must parse clean; a parse failure is a real regression (status "gap").

Run as a module:  python -m fcvs_runner [--verbose]
or import run_corpus() for the regression test.
"""

from __future__ import annotations

import glob
import os
import re

from forterp.dialect import FORTRAN10
from forterp.engine import Engine, Frame, StopExecution
from forterp.parser import parse_units
from forterp.runtime import install_runtime
from forterp.source import expand_includes, scan_file
from forterp.target import PDP10

CORPUS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fcvs")

# The subset of the FCVS corpus that is valid FORTRAN-66 (and runs on this interpreter): the
# routines that predate the F77 features (CHARACTER, block IF, ...). The rest of tests/fcvs/ needs
# F77. This list IS the curation -- F66 runs only these; F77 runs the whole directory. (Numbering
# does not split cleanly -- e.g. FM100-108 need F77 but FM109 is F66 -- so it is enumerated.)
F66_SUBSET = frozenset(
    {
        "FM001.FOR",
        "FM002.FOR",
        "FM003.FOR",
        "FM004.FOR",
        "FM005.FOR",
        "FM006.FOR",
        "FM007.FOR",
        "FM008.FOR",
        "FM009.FOR",
        "FM010.FOR",
        "FM011.FOR",
        "FM012.FOR",
        "FM013.FOR",
        "FM014.FOR",
        "FM016.FOR",
        "FM017.FOR",
        "FM018.FOR",
        "FM019.FOR",
        "FM020.FOR",
        "FM021.FOR",
        "FM022.FOR",
        "FM023.FOR",
        "FM024.FOR",
        "FM025.FOR",
        "FM026.FOR",
        "FM028.FOR",
        "FM030.FOR",
        "FM031.FOR",
        "FM032.FOR",
        "FM033.FOR",
        "FM034.FOR",
        "FM035.FOR",
        "FM036.FOR",
        "FM037.FOR",
        "FM038.FOR",
        "FM039.FOR",
        "FM040.FOR",
        "FM041.FOR",
        "FM042.FOR",
        "FM043.FOR",
        "FM044.FOR",
        "FM045.FOR",
        "FM050.FOR",
        "FM056.FOR",
        "FM060.FOR",
        "FM061.FOR",
        "FM062.FOR",
        "FM080.FOR",
        "FM097.FOR",
        "FM098.FOR",
        "FM099.FOR",
        "FM109.FOR",
    }
)

_PASS = re.compile(r"(\d+)\s+TESTS?\s+PASSED")
# Two FCVS summary dialects report failures differently: the FM0xx/FM1xx audits print
# "nnn ERRORS ENCOUNTERED"; the FM2xx+ audits print "nnn TESTS FAILED". Count both, or a
# routine's failures go silently uncounted (e.g. FM201's "1 TESTS FAILED").
_ERRS = re.compile(r"(\d+)\s+(?:ERRORS?\s+ENCOUNTERED|TESTS?\s+FAILED)")
# FCVS completeness signals: the routine's own count of how many of its declared tests it
# actually executed ("nnn OF nnn TESTS EXECUTED"), plus DELETED / require-INSPECTION tallies
# and the declared total ("THIS PROGRAM HAS nnn TESTS"). Used to assert no early termination:
# a routine that crashed after printing a few passes would otherwise read as "0 failures".
_EXEC = re.compile(r"(\d+)\s+OF\s+(\d+)\s+TESTS?\s+EXECUTED")
# Routines that, by their own design, execute fewer than their declared tests -- a conditional
# block the routine itself gates, NOT an early-termination crash. Maps the routine to the number
# it is EXPECTED to execute. Each is validated against the gfortran golden, which shows the same
# partial count. FM910: tests 2-6 run only "IF DIRECT ACCESS" is supported; gfortran runs 5 of 6.
_EXPECTED_PARTIAL = {"FM910.FOR": 5}
_DELETED = re.compile(r"(\d+)\s+TESTS?\s+(?:WERE\s+)?DELETED")
_INSPECT = re.compile(r"(\d+)\s+TESTS?\s+REQUIRE\s+INSPECTION")
_DECLARED = re.compile(r"THIS PROGRAM HAS\s+(\d+)\s+TESTS")


_CARD = re.compile(r"^CARD\s+(\d+)")


def _card_deck(path):
    """Some FCVS audits (e.g. FM923, list-directed input) document their card-reader input
    deck IN the source as `CARD nn  <image>` comment lines -- 34 card images in cols 1-80,
    with cols 73-80 the sequence field. Reconstruct the deck (a card may span two display
    lines) so the harness can feed it on unit 5; routines without such comments get []."""
    cards = {}
    try:
        with open(path) as fh:
            for ln in fh:
                m = _CARD.match(ln)
                if not m:
                    continue
                num, data = int(m.group(1)), ln[10:72].rstrip()
                cards[num] = (cards[num].rstrip() + " " + data.strip()) if num in cards else data
    except OSError:
        return []
    return [cards[n] for n in sorted(cards)]


def _run_one(path, target=PDP10, dialect=FORTRAN10, character_type=False):
    """Run a single audit routine. Returns (status, passed, errors, meta): status in
    {"run", "gap"}, passed/errors 0 unless status=="run"; meta carries the completeness
    signals (executed / executed_of / deleted / inspect / declared). The curated F66 corpus is
    column-formatted Hollerith, so a parse failure ("gap") is a regression; the F77
    corpus opts into `character_type` (the CHARACTER data type) and treats gaps as
    tracked feature gaps, not regressions."""
    stmts = expand_includes(scan_file(path, dialect=dialect).statements, os.path.dirname(path))
    errs = []
    units = parse_units(stmts, on_error=lambda st, m: errs.append(m), dialect=dialect)
    _NOMETA = {"executed": None, "executed_of": None, "deleted": 0, "inspect": 0, "declared": None}
    if errs:
        return ("gap", 0, 0, _NOMETA)

    main = next((u.name for u in units if u.kind == "program"), None)
    if main is None:
        return ("gap", 0, 0, _NOMETA)
    listing = []  # the line-printer (LPT) buffer
    try:
        # Build + run inside the guard: a build-time crash (e.g. an unsupported DATA
        # construct) counts as a no-summary run, not an aborted corpus. The F66 test
        # pins the exact nosummary set, so a real F66 regression still surfaces.
        eng = Engine(
            {u.name: u for u in units},
            emit=lambda s: None,
            readline=lambda: "",
            printer=listing.append,
            target=target,
            character_type=character_type,
            zero_trip_do=dialect.zero_trip_do,
            blank_null=dialect.blank_null,
        )
        install_runtime(eng)  # STDLIB + FOROTS binary-I/O codec
        # I01 card reader: feed the audit's own embedded card deck (text unit) if it has one
        eng.io[5] = {"lines": _card_deck(path), "pos": 0, "mode": "r", "text": True}
        eng.max_steps = 50_000_000
        eng.run(Frame(eng.rts[main], {}))
    except (StopExecution, Exception):
        pass
    report = "".join(listing)
    mp, me, mx = _PASS.search(report), _ERRS.search(report), _EXEC.search(report)
    md, mi, mt = _DELETED.search(report), _INSPECT.search(report), _DECLARED.search(report)
    meta = {
        "executed": int(mx.group(1)) if mx else None,
        "executed_of": int(mx.group(2)) if mx else None,
        "deleted": int(md.group(1)) if md else 0,
        "inspect": int(mi.group(1)) if mi else 0,
        "declared": int(mt.group(1)) if mt else None,
    }
    return ("run", int(mp.group(1)) if mp else 0, int(me.group(1)) if me else 0, meta)


def run_corpus(
    corpus_dir=CORPUS_DIR, target=PDP10, dialect=FORTRAN10, character_type=False, files=None
):
    """Run FM*.FOR from `corpus_dir`. With `files` (a set/iterable of basenames) restrict the run
    to that subset -- the FCVS corpus is one set, but only F66_SUBSET is valid FORTRAN-66, so the
    F66 driver passes that subset while the F77 driver runs all. Returns the aggregate + detail."""
    run = {}
    gap, nosummary, incomplete, inspect_routines = [], [], [], []
    total_pass = total_err = n_checked = 0
    chosen = set(files) if files is not None else None
    for path in sorted(glob.glob(os.path.join(corpus_dir, "FM*.FOR"))):
        name = os.path.basename(path)
        if chosen is not None and name not in chosen:
            continue
        status, p, e, meta = _run_one(path, target, dialect, character_type)
        if status == "gap":  # parse failure -> regression (curated F66)
            gap.append(name)
            continue
        run[name] = (p, e)
        total_pass += p
        total_err += e
        if p == 0 and e == 0:
            nosummary.append(name)  # ran, but printed no PASS/ERR summary
        # Completeness: did the routine run EVERY test it claims? A routine that crashed after
        # a few passes would otherwise read as "0 failures". FCVS states this two ways:
        #  - modern audits print "X OF Y TESTS EXECUTED" -> require X == Y;
        #  - older self-checkers (a PASS/FAIL tally + a declared total, no EXECUTED line) ->
        #    require pass+fail+deleted+inspect == the declared total.
        # Print-and-eyeball routines (no tally, no EXECUTED line) are validated by the gfortran
        # goldens instead (test_fcvs_golden.py), so they are not reconciled here.
        if meta[
            "inspect"
        ]:  # has require-INSPECTION tests -> only the gfortran golden validates them
            inspect_routines.append(name)
        if meta["executed_of"] is not None:
            n_checked += 1
            expected = _EXPECTED_PARTIAL.get(name, meta["executed_of"])  # design-gated partials
            if meta["executed"] != expected:
                incomplete.append(f"{name}: ran {meta['executed']} of {meta['executed_of']}")
        elif meta["declared"] is not None and (p + e) > 0:
            n_checked += 1
            accounted = p + e + meta["deleted"] + meta["inspect"]
            if accounted != meta["declared"]:
                incomplete.append(
                    f"{name}: {accounted} accounted of {meta['declared']} declared "
                    f"(pass {p} fail {e} del {meta['deleted']} insp {meta['inspect']})"
                )
    return {
        "run": run,
        "gap": gap,
        "nosummary": nosummary,
        "incomplete": incomplete,
        "inspect_routines": inspect_routines,  # routines with require-INSPECTION tests
        "n_checked": n_checked,  # routines whose completeness was actually reconciled
        "n_run": len(run),
        "n_gap": len(gap),
        "total_pass": total_pass,
        "total_err": total_err,
    }


def main(argv=None):
    import sys

    verbose = "--verbose" in (argv or sys.argv[1:])
    r = run_corpus(files=F66_SUBSET)  # the F66-valid subset (the F77 routines need the F77 driver)
    print(
        f"FCVS F66 corpus: {r['n_run']} routines run, {r['n_gap']} parse-failure(s) (should be 0)"
    )
    print(f"  conformance TESTS PASSED: {r['total_pass']}")
    print(
        f"  ERRORS ENCOUNTERED:       {r['total_err']}  "
        f"(FM001 forces one FAIL by design: 'FORCE FAIL CODE TO BE EXECUTED')"
    )
    if r["nosummary"]:
        print(f"  ran w/o a PASS/ERR summary (print-and-eyeball FORMAT tests): {r['nosummary']}")
    if verbose:
        for name, (p, e) in sorted(r["run"].items()):
            flag = "  <-- FAIL" if e else ""
            print(f"    {name}: {p} passed, {e} errors{flag}")
        if r["gap"]:
            print(f"  parse failures (regressions!): {r['gap']}")
    return r


if __name__ == "__main__":
    main()
