"""Conformance baseline over the F77 FCVS corpus (tests/fcvs77/).

These are the 140 FCVS audit routines that use the FORTRAN-77 CHARACTER type (and the
F77 control-flow / I/O features) -- the set removed when tests/fcvs/ was curated to
F66-only. They are restored verbatim from history and run under the F77 dialect on the
NATIVE target with character_type on.

The corpus is gfortran-clean: every file compiles under
`gfortran -fsyntax-only -std=legacy -ffixed-form`. (The original vendoring had prepended
a bogus second `PROGRAM FMnnn` line to the 40 routines that test the PROGRAM statement --
gfortran and forterp both rejected the duplicate; that single synthetic line was removed
to recover pristine FCVS, verified against gfortran. Nothing else was touched.)

All 140 routines parse and run under the F77 front-end (the front-end work is complete:
zero parse-gaps). What remains is value/semantic conformance: of the 140, the self-checking
routines report 1546 sub-tests PASS and 108 FAIL (across 21 routines), and 43 are
print-and-eyeball (no PASS/FAIL summary -- validated separately against gfortran goldens,
see test_fcvs77_golden.py).

NOTE: these failures were masked until the runner learned the FM2xx+ summary verb -- those
audits print "nnn TESTS FAILED", not "nnn ERRORS ENCOUNTERED", so their failures went
uncounted. They are a real punch-list (numeric precision, INQUIRE, formatting); the count is
pinned here and ratchets DOWN as bugs are fixed (INQUIRE ACCESS/FORM specifiers cleared FM915).

Landed since the restore: IMPLICIT CHARACTER*<len> (the audit-harness preamble), the
optional comma after a DO label, LOGICAL/COMPLEX PARAMETER constants, the widthless A
descriptor, list-directed I/O and .EQV./.NEQV. (each split into its own dialect flag), the
keyword=value I/O control list, OPEN's positional unit + keyword specifiers, blank COMMON //
spellings, CHARACTER*(<param>) parametrised length, the F77 array-bound ':' (vs DEC '/')
reading, correct CHARACTER DATA init + DATA substrings, blanks within a dotted operator
(. NE .), and assumed-size array declarators A(...,*).
"""

import glob
import os

from fcvs_runner import run_corpus

from forterp.dialect import F77
from forterp.target import NATIVE

CORPUS77 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fcvs77")
R = run_corpus(corpus_dir=CORPUS77, target=NATIVE, dialect=F77, character_type=True)


def test_corpus_is_the_full_restored_f77_set():
    # All 140 F77/CHARACTER FCVS routines are present (restored from history).
    assert len(glob.glob(os.path.join(CORPUS77, "FM*.FOR"))) == 140


def test_f77_corpus_fully_parses_and_runs():
    # Every restored F77 routine parses and runs -- no parse-gaps remain.
    assert R["n_gap"] == 0
    assert R["n_run"] == 140


def test_f77_conformance_baseline():
    # Pinned baseline. A change means real behavior moved: update these in lockstep with
    # the fix (a gain) or investigate (a regression).
    assert R["n_run"] == 140
    assert R["n_gap"] == 0
    assert R["total_pass"] == 1546
    assert R["total_err"] == 108
    assert len(R["nosummary"]) == 43


def test_self_check_failures_do_not_grow():
    # The known self-check failures (value/semantic conformance, not parse/control-flow).
    # A ratchet: fixing a bug should LOWER this -- update it down, never silently up.
    assert R["total_err"] <= 108
