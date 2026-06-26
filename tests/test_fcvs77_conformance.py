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
using the list item's declared length on both output and input -- including a repeated
widthless A (4A) reading CHARACTER items of differing lengths, where the reader pops each
field width from the io-list (13.5.11) -- for FM402, an intrinsic name (declared INTRINSIC)
passed as an actual argument and dispatched through the dummy (X3.9-1978 15.10) for FM317/FM328,
coercing a
statement function's value to the function's own implicit type (an INTEGER-named SF
truncates a real body result, 15.4.1) for FM351, and INQUIRE(EXIST=) reporting true for a
connected file with no disk backing yet (a DIRECT scratch file) for FM921, and direct-access
FORMATTED file I/O for FM912 -- a '/'-bearing FORMAT splits one WRITE across consecutive
direct-access records (so NEXTREC advances by the record count, 12.9.4.2), and a direct-access
file's records now persist on CLOSE and reload on a STATUS='OLD' reopen, and a zero-trip inner
DO sharing its terminal label with an enclosing active DO (a shared-terminal nest) now drives
the outer loop's incrementation without executing the shared terminal statement (11.10) for
FM256, and converting a DO loop's parameters to the DO variable's type before forming the
iteration count (an integer DO variable with real bounds, DO I=6.7,9.325, truncates to 6,9,1
-> 4 trips; 11.10.2) for FM719, and the E/F edit-descriptor fixes for FM406 (and unblocking
FM405 out of the no-summary set): an F field whose value rounds to zero drops the minus sign,
an E field drops its optional leading zero to fit a narrow width, and Ew.dEe / Gw.dEe give the
exponent exactly e digits (13.5.9) -- the last also clearing FM912 sub-tests. FM912
(direct-access formatted I/O) then fully cleared with the rest of its edit descriptors: Iw.m
minimum digits, SP/S/SS sign control, TL/TR relative tabs, the colon (terminate format control
when the io-list is exhausted), and -- the real engine fix -- a CHARACTER substring lvalue
S(lo:hi) as an I/O-list item / actual argument now writes back through a SubstringRef instead
of being dropped on a read-only temporary.

FM923 (list-directed input, 26) then cleared too. Its card-reader input deck is documented IN
the source as `CARD nn` comment images (34 cards, cols 1-80); the runner reconstructs it and
feeds it on unit 5, and the list-directed reader was rebuilt to the X3.9-1978 13.6 grammar:
type-driven conversion (INTEGER/REAL/LOGICAL/CHARACTER per the io-list element), a quote-aware
tokenizer (a '...' value keeps embedded blanks/commas/slashes, '' -> '), null values (`,,`),
repeats (`r*c` / `r*`), the `/` terminator, and multi-record spanning (a READ consumes as many
records as its list needs).

FM411 (sequential-file positioning, 2) then cleared by modeling the endfile record: ENDFILE
writes an endfile MARKER (X3.9-1978 12.10.4.2) rather than truncating, so a following BACKSPACE
backs over that marker -- not over a real data record -- and ENDFILE+BACKSPACE+WRITE rebuilds
the file to the expected 142 records (a READ reaching the marker still hits END=).

FM302 (COMMON/EQUIVALENCE storage association, 8) then cleared, taking the corpus to zero
self-check failures. The bug was localized, not the value model's width limitation (FM302's
COMMON is all INTEGER/REAL/LOGICAL): a block's storage is the concatenation of every COMMON
declaration for it in a unit (8.3), but the layout reset the offset to 0 per COMMON
statement/segment, so a block declared across several statements (blank COMMON here spans five)
overlapped at offset 0. The running offset is now tracked per block, so the multi-statement
declarations append -- and positional association across units (renaming, viewing blank COMMON
as one array) lines up.

With that, every self-checking F77 FCVS routine reports zero errors; the print-and-eyeball
routines are validated separately against gfortran goldens (test_fcvs77_golden.py).

Output-conformance (golden) work since then: FM500 (BLOCK DATA) now matches gfortran -- a DATA
n*value repeat count may be a PARAMETER, not a literal (DATA D(1),D(2)/IPN001*x/), and a
CHARACTER PARAMETER used as a DATA value (PARAMETER(APK='X'); DATA C/n*APK/) is kept as text
and fit to the target rather than packed as a Hollerith word too early.

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
    assert R["total_pass"] == 1750
    assert R["total_err"] == 0  # the entire self-checking F77 FCVS corpus passes
    assert len(R["nosummary"]) == 39


def test_self_check_failures_do_not_grow():
    # The known self-check failures (value/semantic conformance, not parse/control-flow).
    # A ratchet: fixing a bug should LOWER this -- update it down, never silently up.
    assert R["total_err"] <= 0


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
    assert R["n_checked"] == 77


def test_inspection_tests_are_all_golden_validated():
    # A require-INSPECTION sub-test prints a value the program can't self-judge (PASS/FAIL), so
    # its ONLY validation is the gfortran golden. If such a routine drifts onto the divergent
    # punch-list, those inspection results become unverified -- guard against that here. (Today
    # all 9 INSPECT-bearing routines match gfortran exactly.)
    from test_fcvs77_golden import KNOWN_DIVERGENT

    insp = [n[:-4] for n in R["inspect_routines"]]  # strip ".FOR"
    assert len(insp) == 11
    unverified = sorted(n for n in insp if n in KNOWN_DIVERGENT)
    assert not unverified, f"INSPECT routines whose output is NOT golden-validated: {unverified}"
