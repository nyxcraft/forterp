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

Unlike the F66 corpus, this one is a WORK-IN-PROGRESS baseline: F77 support is partial,
so parse "gaps" here are *tracked feature gaps*, not regressions. The numbers below are
pinned so that both regressions and improvements are visible and force a conscious update.

Current gaps (18 files fail to parse under the F77 front-end -- mostly the F77 I/O set):
   5  keyword=value in an I/O control list   -- READ(UNIT=u, FMT=f, ...)
   4  list-directed I/O (*)                  -- standardized in F77, still gated under the
                                               DEC-only extended_io knob
   2  bare ',' where an identifier is expected -- OPEN(u, ACCESS=..., RECL=...)
   2  substring ':' in a DATA target
   2  blanks within a .NE./.EQ. operator     -- "C10VK. NE. 'YES'"
   1  blank COMMON //
   1  CHARACTER*(<param>) parametrised length
   1  .EQV. / .NEQV. logical operators       -- F77 standard, gated under DEC dec_operators
Of the 122 that run: 1258 sub-tests PASS, 155 ERRORS, 41 print-and-eyeball (no summary).

Landed since the restore: IMPLICIT CHARACTER*<len> (the audit-harness preamble, +30
routines / +467 sub-tests), the optional comma after a DO label, LOGICAL/COMPLEX PARAMETER
constants, and the widthless A descriptor.
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


def test_f77_conformance_baseline():
    # Pinned WIP baseline. When an F77 feature lands, these numbers move up -- update
    # them here in lockstep with the fix so the gain is recorded, not silently absorbed.
    assert R["n_run"] == 122
    assert R["n_gap"] == 18
    assert R["total_pass"] == 1258
    assert R["total_err"] == 155
    assert len(R["nosummary"]) == 41


def test_running_routines_mostly_pass():
    # Sanity floor independent of the exact pins: the routines that DO parse are
    # overwhelmingly passing their self-checks (>80% of sub-tests), so the F77 features
    # we have implemented are behaving, not just parsing.
    assert R["total_pass"] > 4 * R["total_err"]
