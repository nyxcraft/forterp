"""Regression over the curated F66 FCVS corpus (tests/fcvs/).

Runs the FORTRAN-66 audit routines through the interpreter and pins the aggregate
result. The corpus is curated: only the FCVS routines that are valid F66 and run on
this interpreter are kept -- the F77 (CHARACTER) routines were removed from the
original 192-file set, so every file here parses and runs. FCVS is independent of our
own assumptions (it predates this project by ~40 years), so a regression here catches
conformance drift our own hand-written tests (test_f66_conformance.py) might share a
blind spot with.

These numbers are the locked-in baseline; a change means real behavior moved.
"""

from fcvs_runner import run_corpus
from f66.target import NATIVE
from f66.dialect import STRICT_F66

R = run_corpus()  # default: FORTRAN10 dialect, PDP10 target
R_NATIVE = run_corpus(target=NATIVE)  # value-model axis
R_STRICT = run_corpus(dialect=STRICT_F66)  # front-end dialect axis (ANSI, DEC ext off)


def test_curated_corpus_all_parses_and_runs():
    # Every file in the curated corpus must parse clean and run -- a parse failure is a
    # regression, not "out of scope" (the F77 routines were removed). 52 routines today;
    # this guards against re-introducing non-runnable source.
    import glob
    import os
    from fcvs_runner import CORPUS_DIR

    n_files = len(glob.glob(os.path.join(CORPUS_DIR, "FM*.FOR")))
    assert R["n_gap"] == 0  # nothing fails to parse
    assert R["n_run"] == n_files  # every file ran
    assert R["n_run"] == 52  # the current curated count


def test_blanks_insignificance_files_run_and_pass():
    # The 3.1.6 audit routines now run; they self-check, so passing means our
    # blanks-within-tokens handling (DIM EN SION / 3 2 7 6 7 / K 5 6 78  9) is correct.
    for f in ("FM010.FOR", "FM011.FOR", "FM021.FOR"):
        passed, errors = R["run"][f]
        assert passed > 0 and errors == 0, (f, passed, errors)


def test_total_conformance_tests_passed():
    assert R["total_pass"] == 1146


def test_only_expected_failure_is_fm001_by_design():
    # The single ERROR is FM001 TEST 002, labelled "FORCE FAIL CODE TO BE
    # EXECUTED" -- the suite's self-test of its own fail-reporting path
    # (COMPUTED == CORRECT == 2). No genuine conformance failures.
    assert R["total_err"] == 1
    assert R["run"]["FM001.FOR"][1] == 1


def test_print_and_eyeball_files_have_no_autocheck():
    # FM005/FM109 print values under FORMAT descriptors for visual inspection;
    # they self-report no PASS/FAIL summary. Documented, not a failure.
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
    # turning the DEC front-end off (STRICT_F66: no octal "nnn, tab-format, inline !,
    # lenient 72-col) must not change what parses or passes. This is the dialect-axis
    # analog of the NATIVE-target run, and validates STRICT_F66 against real ANSI code.
    assert R_STRICT["n_run"] == R["n_run"]
    assert R_STRICT["total_pass"] == R["total_pass"]
    assert R_STRICT["total_err"] == R["total_err"]
    assert set(R_STRICT["nosummary"]) == set(R["nosummary"])
