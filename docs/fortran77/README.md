# The FORTRAN 77 reference manual

A complete, example-driven reference for the **FORTRAN 77** language — ANSI X3.9-1978, the full
language (not the subset level). It is written for people who want to *read and write* FORTRAN 77,
whether to maintain vintage code or to understand what a classic program does. Every feature is
shown with a small, runnable example and its result.

This manual is self-contained: you do not need to know an earlier FORTRAN to use it. It runs on
[`forterp`](../../README.md); each chapter ends with a **forterp notes** box describing anything
specific to how forterp implements that part of the language (and which knobs change it). For how
to *select and run* the F77 dialect, see the [Python API guide](../API.md) and [CLI.md](../CLI.md).

## How to read this manual

- Chapters follow the structure of the standard, but you can read them in any order — they
  cross-reference each other.
- Code is shown in **fixed source form** (the classic column layout explained in
  [Chapter 3](03-source-form.md)). Expected output appears in a trailing comment.
- A box marked **forterp notes** flags behavior particular to forterp — an enforced rule, a
  supported extension, or a tunable default. These never change what a standard-conforming
  program means; they tell you what to expect at the edges.
- Section numbers in parentheses, e.g. *(§6.1.5)*, point at the standard for authority.

## Contents

**The basics**
1. [Overview & program structure](01-overview.md)
2. [Language elements & concepts](02-language-elements.md)
3. [Source form](03-source-form.md)
4. [Data types & constants](04-data-types.md)

**Building blocks**
5. [Arrays & substrings](05-arrays-substrings.md)
6. [Expressions & operators](06-expressions.md)
7. [Statements at a glance](07-statements.md)
8. [Specification statements](08-specification.md)

**Giving values & doing work**
9. [The `DATA` statement](09-data.md)
10. [Assignment](10-assignment.md)
11. [Control statements](11-control.md)

**Input & output**
12. [Input / output](12-io.md)
13. [`FORMAT` & edit descriptors](13-format.md)

**Program units**
14. [Main program](14-main-program.md)
15. [Functions & subroutines](15-procedures.md)
16. [Block data](16-block-data.md)

**The formal model**
17. [Storage association & definition](17-association.md)
18. [Scopes & symbolic names](18-scopes.md)

**Appendices**
- A. [Intrinsic function reference](A-intrinsics.md)
- B. [Edit-descriptor quick reference](B-edit-descriptors.md)
- C. [Operator precedence & the collating sequence](C-precedence-ascii.md)
- D. [forterp extensions & strict gates](D-forterp-extensions.md)
- E. [Differences from FORTRAN 66](E-differences-f66.md)
