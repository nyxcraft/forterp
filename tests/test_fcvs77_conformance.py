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

All 140 routines parse and run under the F77 front-end, and every self-checking routine
passes with ZERO errors. The numbers below are pinned so any regression is visible.

Of the 140 that run: 1543 sub-tests PASS, 0 ERRORS. The other 51 routines are
print-and-eyeball (they print values for visual inspection and report no PASS/FAIL
summary), so they contribute no self-checked sub-tests -- validating their output is
separate work (a differential check against gfortran).

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
    assert R["total_pass"] == 1543
    assert R["total_err"] == 0
    assert len(R["nosummary"]) == 51


def test_no_self_check_errors():
    # Every self-checking routine passes: zero conformance errors across the corpus.
    assert R["total_err"] == 0
