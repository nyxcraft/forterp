"""Regression over the FORTRAN-66-valid subset of the FCVS corpus (tests/fcvs/).

FCVS is one 192-routine corpus (tests/fcvs/); this driver runs the F66_SUBSET of it -- the
routines that are valid FORTRAN-66 (the rest need F77 features like CHARACTER and are exercised
by test_fcvs_f77_conformance.py, which runs the whole directory under F77). Pins the aggregate
result. FCVS is independent of our own assumptions (it predates this project by ~40 years), so a
regression here catches conformance drift our own hand-written tests (test_f66_conformance.py)
might share a blind spot with.

These numbers are the locked-in baseline; a change means real behavior moved.
"""

from fcvs_runner import F66_SUBSET, run_corpus

from forterp.dialect import F66
from forterp.target import NATIVE

R = run_corpus(files=F66_SUBSET)  # default: FORTRAN10 dialect, PDP10 target
R_NATIVE = run_corpus(target=NATIVE, files=F66_SUBSET)  # value-model axis
R_STRICT = run_corpus(dialect=F66, files=F66_SUBSET)  # front-end dialect axis (ANSI, DEC ext off)


def test_curated_corpus_all_parses_and_runs():
    # Every routine in the F66_SUBSET must parse clean and run under F66 -- a parse failure is a
    # regression, not "out of scope." This guards against the subset listing a non-F66 routine.
    assert R["n_gap"] == 0  # nothing fails to parse
    assert R["n_run"] == len(F66_SUBSET)  # every selected file ran
    assert R["n_run"] == 52  # the current F66-valid count


def test_blanks_insignificance_files_run_and_pass():
    # The 3.1.6 audit routines now run; they self-check, so passing means our
    # blanks-within-tokens handling (DIM EN SION / 3 2 7 6 7 / K 5 6 78  9) is correct.
    for f in ("FM010.FOR", "FM011.FOR", "FM021.FOR"):
        passed, errors = R["run"][f]
        assert passed > 0 and errors == 0, (f, passed, errors)


def test_total_conformance_tests_passed():
    assert R["total_pass"] == 1149


def test_no_genuine_failures_fm001_force_fail_is_a_negative_pass():
    # FM001 TEST 002, labelled "FORCE FAIL CODE TO BE EXECUTED", is a NEGATIVE assertion --
    # the suite's self-test of its own fail-reporting path (COMPUTED == CORRECT == 2). The runner
    # reclassifies that by-design failure as a pass (FM001 -> 2 passed, 0 errors), so the corpus
    # has zero genuine conformance failures and ANY error is a regression.
    assert R["total_err"] == 0
    assert R["run"]["FM001.FOR"] == (2, 0)


def test_print_and_eyeball_files_have_no_autocheck():
    # FM005/FM109 print values under FORMAT descriptors for visual inspection;
    # they self-report no PASS/FAIL summary. Documented, not a failure. This set is also the
    # completeness guard for this curated F66 corpus: its older audits print "nnn ERRORS
    # ENCOUNTERED" but no "THIS PROGRAM HAS nnn TESTS"/"X OF Y EXECUTED" line to reconcile
    # against, so a mid-run crash surfaces as a routine dropping into `nosummary` (which this
    # pins), not as a silent partial pass. (The F77 corpus has the explicit EXECUTED line --
    # see test_fcvs_f77_conformance.test_every_routine_runs_all_its_declared_tests.)
    assert set(R["nosummary"]) == {"FM005.FOR", "FM109.FOR"}


def test_native_target_runs_the_corpus_identically():
    # The portable NATIVE target (the library default) runs the same ANSI F66 audit
    # corpus with the identical aggregate -- standard-conformance assertions do not
    # depend on PDP-10 quirks (36-bit wrap, .TRUE.=-1, 5x7-bit packing). This gives the
    # DEFAULT target real, independent conformance coverage.
    assert R_NATIVE["n_run"] == R["n_run"]
    assert R_NATIVE["total_pass"] == R["total_pass"]
    assert R_NATIVE["total_err"] == R["total_err"]
    assert set(R_NATIVE["nosummary"]) == set(R["nosummary"])


def test_strict_f66_dialect_runs_the_corpus_identically():
    # The FCVS audits are pure ANSI X3.9-1966 (they predate the DEC extensions), so
    # turning the DEC front-end off (F66: no octal "nnn, tab-format, inline !,
    # lenient 72-col) must not change what parses or passes. This is the dialect-axis
    # analog of the NATIVE-target run, and validates F66 against real ANSI code.
    assert R_STRICT["n_run"] == R["n_run"]
    assert R_STRICT["total_pass"] == R["total_pass"]
    assert R_STRICT["total_err"] == R["total_err"]
    assert set(R_STRICT["nosummary"]) == set(R["nosummary"])
