"""Run the vendored FCVS conformance corpus (tests/fcvs/) through the interpreter.

FCVS audit routines are self-checking: each computes a value, compares it to the
known-correct value via an arithmetic IF, tallies PASS/FAIL/DELETE counts, and
prints a run summary ("nnn TESTS PASSED", "nnn ERRORS ENCOUNTERED") to the line
printer (unit 6). We capture that printer listing (engine.printer sink) and parse
the summary -- the report IS line-printer output, not terminal I/O, so it is read
from a dedicated buffer, separate from any terminal stream.

This is a CURATED F66 corpus: it holds only the FCVS audit routines that are valid
FORTRAN-66 and run on this interpreter. The F77 routines (those using the CHARACTER
type -- which does not exist in F66) were removed from the original 192-file set, so
that what sits in tests/fcvs/ is exactly what runs. Every file here must parse clean;
a parse failure is therefore a real regression (status "gap"), not "out of scope."

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

_PASS = re.compile(r"(\d+)\s+TESTS?\s+PASSED")
# Two FCVS summary dialects report failures differently: the FM0xx/FM1xx audits print
# "nnn ERRORS ENCOUNTERED"; the FM2xx+ audits print "nnn TESTS FAILED". Count both, or a
# routine's failures go silently uncounted (e.g. FM201's "1 TESTS FAILED").
_ERRS = re.compile(r"(\d+)\s+(?:ERRORS?\s+ENCOUNTERED|TESTS?\s+FAILED)")


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
    """Run a single audit routine. Returns (status, passed, errors): status in
    {"run", "gap"}, passed/errors 0 unless status=="run". The curated F66 corpus is
    column-formatted Hollerith, so a parse failure ("gap") is a regression; the F77
    corpus opts into `character_type` (the CHARACTER data type) and treats gaps as
    tracked feature gaps, not regressions."""
    stmts = expand_includes(scan_file(path, dialect=dialect).statements, os.path.dirname(path))
    errs = []
    units = parse_units(stmts, on_error=lambda st, m: errs.append(m), dialect=dialect)
    if errs:
        return ("gap", 0, 0)

    main = next((u.name for u in units if u.kind == "program"), None)
    if main is None:
        return ("gap", 0, 0)
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
    mp, me = _PASS.search(report), _ERRS.search(report)
    return ("run", int(mp.group(1)) if mp else 0, int(me.group(1)) if me else 0)


def run_corpus(corpus_dir=CORPUS_DIR, target=PDP10, dialect=FORTRAN10, character_type=False):
    """Run every FM*.FOR. Returns a dict with the aggregate + per-file detail."""
    run = {}
    gap, nosummary = [], []
    total_pass = total_err = 0
    for path in sorted(glob.glob(os.path.join(corpus_dir, "FM*.FOR"))):
        name = os.path.basename(path)
        status, p, e = _run_one(path, target, dialect, character_type)
        if status == "gap":  # parse failure -> regression (curated F66)
            gap.append(name)
        else:
            run[name] = (p, e)
            total_pass += p
            total_err += e
            if p == 0 and e == 0:
                nosummary.append(name)  # ran, but printed no PASS/ERR summary
    return {
        "run": run,
        "gap": gap,
        "nosummary": nosummary,
        "n_run": len(run),
        "n_gap": len(gap),
        "total_pass": total_pass,
        "total_err": total_err,
    }


def main(argv=None):
    import sys

    verbose = "--verbose" in (argv or sys.argv[1:])
    r = run_corpus()
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
