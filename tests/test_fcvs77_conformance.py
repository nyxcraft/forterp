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
routines report 1594 sub-tests PASS and 60 FAIL (across 12 routines), and 43 are
print-and-eyeball (no PASS/FAIL summary -- validated separately against gfortran goldens,
see test_fcvs77_golden.py).

These failures were masked until the runner learned the FM2xx+ summary verb ("nnn TESTS
FAILED", not "nnn ERRORS ENCOUNTERED"). The count is pinned and ratchets DOWN as bugs are
fixed. Cleared so far: the INQUIRE specifier work (ACCESS/FORM/SEQUENTIAL/DIRECT/RECL/NEXTREC/
BLANK + the filename strip) for FM914-922, and blanks before a numeric exponent (`1545 E7` ->
1545E7, resolved in the expression parser so a CHARACTER*<len> length or DO label is untouched)
for FM201/FM351/FM352, F77 zero-trip DO loops + the post-loop index value (X3.9-1978 11.10,
dialect-gated -- F66/FORTRAN-10 keep one-trip) for FM256, and the optional leading decimal
point in an L-format read (".TRUE." reads true) for FM401, and the widthless A descriptor
using the list item's length (a CHARACTER*1 takes one column, not the default 5) on both
output and input for FM402, an intrinsic name (declared INTRINSIC) passed as an actual
argument and dispatched through the dummy (X3.9-1978 15.10) for FM317/FM328, coercing a
statement function's value to the function's own implicit type (an INTEGER-named SF
truncates a real body result, 15.4.1) for FM351, and INQUIRE(EXIST=) reporting true for a
connected file with no disk backing yet (a DIRECT scratch file) for FM921, and direct-access
FORMATTED file I/O for FM912 -- a '/'-bearing FORMAT splits one WRITE across consecutive
direct-access records (so NEXTREC advances by the record count, 12.9.4.2), and a direct-access
file's records now persist on CLOSE and reload on a STATUS='OLD' reopen, and a zero-trip inner
DO sharing its terminal label with an enclosing active DO (a shared-terminal nest) now drives
the outer loop's incrementation without executing the shared terminal statement (11.10) for
FM256.

One large remaining cluster is NOT an interpreter bug: FM923 (26) reads its list-directed data
from the card reader (unit I01), and FCVS supplies that input as a separate data deck the
harness does not vendor -- every READ comes back empty. FM912's 5 remaining failures are real:
advanced FORMAT edit descriptors (Gw.dEe / Ew.dEe explicit exponent width, T/TL/TR tabbing,
SP/S/SS sign control, nP scale on input, BZ/BN blank control).

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
    assert R["total_pass"] == 1606
    assert R["total_err"] == 48
    assert len(R["nosummary"]) == 43


def test_self_check_failures_do_not_grow():
    # The known self-check failures (value/semantic conformance, not parse/control-flow).
    # A ratchet: fixing a bug should LOWER this -- update it down, never silently up.
    assert R["total_err"] <= 48
