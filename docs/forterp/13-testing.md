# Testing

Tests run through the **real pipeline** (source reader → lexer → parser → engine), never
against internal mocks — see `tests/conftest.py` (`run()`/`run_int()` compile a snippet and
hand back the `Engine` to inspect COMMON). Conformance is the **FCVS** corpus
(`tests/fcvs/`, driven by `tests/fcvs_runner.py`): each audit routine is self-checking and
prints a PASS/ERROR tally to the line printer, which the runner captures and parses. The
corpus is the **full 192-routine FCVS set** (pristine from the public-domain NIST suite,
with the canonical `.DAT` input decks): every file parses and runs, so a parse failure is a
regression, not "out of scope." `test_fcvs_f66_conformance.py` runs the F66-valid subset
(`F66_SUBSET`, 52 routines) under `F66`; `test_fcvs_f77_conformance.py` runs all 192 under
`F77`; both also run under both value-model targets (`NATIVE` and `PDP10`) and produce the
identical aggregate — independent evidence both seams preserve standard behavior. On top of
the self-check, `test_fcvs_golden.py` is a **second, independent oracle**: a byte-for-byte
diff against committed gfortran (`-std=legacy`) output (`tests/fcvs_golden/`), so the
print-and-eyeball routines that carry no PASS/FAIL tally are still validated.

Card-reader input comes from the canonical NIST `<NAME>.DAT` decks vendored beside each `.FOR`
(one 80-column card per line), not the lossy `CARD nn` image comments. Every routine sits in
exactly one validation bucket (enforced by `test_whole_corpus_is_accounted_for`): a *byte-match*
against the golden (the large majority), a *value-token* compare where list-directed field widths
are processor-dependent (FM905/907), the routine's *own self-check* where gfortran is an unreliable
oracle (FM257, FM406), or the single documented `KNOWN_GF_DIFF` (FM111, where gfortran is the
outlier on an `F2.1` overflow). With the correct decks gfortran runs the whole 192-routine corpus
and **forterp byte-matches 191 of 192**; the self-checking routines report **zero failures**
(FM001's "force fail" test is a negative assertion the runner counts as a pass by design). The full
suite passes standalone (747 tests), no gfortran needed at test time.

---
