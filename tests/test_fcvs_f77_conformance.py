"""Conformance baseline: the WHOLE FCVS corpus (tests/fcvs/, 192 routines) under FORTRAN-77.

FCVS is one corpus; FORTRAN-77 is valid against ALL of it (the F66-valid subset, F66_SUBSET, is
also exercised under F66 by test_fcvs_f66_conformance.py). Every routine parses and runs -- zero
parse-gaps -- and the self-checking ones report zero GENUINE failures. FM001 TEST 002 is a NEGATIVE
assertion ("FORCE FAIL CODE TO BE EXECUTED", the suite's self-test of its own fail-reporting path);
the runner reclassifies that by-design failure as a pass, so total_err is a true 0. The
print-and-eyeball routines carry no PASS/FAIL summary and are validated separately against
gfortran goldens (test_fcvs_golden.py).

The aggregate is pinned and ratchets: a change means real behavior moved -- a gain (update in
lockstep) or a regression (investigate). The deep history of each fix lives in the CHANGELOG / git.
"""

import glob
import os

from fcvs_runner import CORPUS_DIR, run_corpus

from forterp.dialect import F77
from forterp.target import NATIVE

R = run_corpus(target=NATIVE, dialect=F77, character_type=True)  # the whole corpus, under F77


def test_corpus_is_the_full_fcvs_set():
    # The whole FCVS corpus lives in tests/fcvs/ (F66-valid + F77-only, merged): 192 routines.
    assert len(glob.glob(os.path.join(CORPUS_DIR, "FM*.FOR"))) == 192


def test_f77_corpus_fully_parses_and_runs():
    # Every routine parses and runs under F77 -- no parse-gaps anywhere in the corpus.
    assert R["n_gap"] == 0
    assert R["n_run"] == 192


def test_f77_conformance_baseline():
    # Pinned baseline. A change means real behavior moved: update these in lockstep with
    # the fix (a gain) or investigate (a regression).
    assert R["n_run"] == 192
    assert R["n_gap"] == 0
    assert R["total_pass"] == 3349
    assert R["total_err"] == 0  # zero genuine failures (FM001's force-fail is a negative-test pass)
    assert len(R["nosummary"]) == 17


def test_self_check_failures_do_not_grow():
    # Zero GENUINE self-check failures across the whole corpus. FM001 TEST 002, labelled
    # "FORCE FAIL CODE TO BE EXECUTED", is a NEGATIVE assertion -- the suite testing its own
    # fail-reporting path -- so the runner reclassifies that one by-design failure as a pass
    # (FM001 reports 2 passed, 0 errors). A hard ratchet: ANY error here is now a regression.
    assert R["total_err"] == 0
    assert R["run"]["FM001.FOR"] == (2, 0)


def test_every_routine_runs_all_its_declared_tests():
    # Completeness, not just correctness: a routine that crashed after a few passes would read
    # as "0 failures". Enforce FCVS's own accounting -- "X OF Y TESTS EXECUTED" must have X==Y,
    # and a self-checker's pass+fail+deleted+inspect must equal its declared total. Empty means
    # no routine terminated early. (Print-and-eyeball routines are golden-validated separately.)
    assert R["incomplete"] == [], "routines that did not run every declared test:\n" + "\n".join(
        R["incomplete"]
    )
    # Non-vacuity: the check actually reconciled a substantial set (the routines printing FCVS's
    # "X OF Y TESTS EXECUTED"). Older self-checkers lack that line, but a mid-run crash there
    # prints no summary at all and so moves the pinned `nosummary` set instead.
    assert R["n_checked"] == 103


def test_inspection_tests_are_all_golden_validated():
    # A require-INSPECTION sub-test prints a value the program can't self-judge (PASS/FAIL), so its
    # only validation is the gfortran golden. Every INSPECT-bearing routine must therefore be
    # golden-validated (in MATCHING) OR a documented KNOWN_GF_DIFF (its eyeball-only output differs
    # for a recorded reason). One that is neither has silently-unverified inspection output.
    from test_fcvs_golden import KNOWN_GF_DIFF, MATCHING

    insp = [n[:-4] for n in R["inspect_routines"]]  # strip ".FOR"
    assert len(insp) == 16
    unverified = sorted(n for n in insp if n not in MATCHING and n not in KNOWN_GF_DIFF)
    assert not unverified, f"INSPECT routines neither golden-validated nor documented: {unverified}"
