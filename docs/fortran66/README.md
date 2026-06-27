# The FORTRAN 66 reference manual

A complete, example-driven reference for the **FORTRAN 66** language — USA Standard X3.9-1966, the
original standard FORTRAN — together with the **DEC FORTRAN-10** extensions that real PDP-10 code
relied on. It is the strict base dialect — the language most 1960s–70s decks were written in; select it with `--std f66` or `dialect=forterp.F66` (the default is now FORTRAN 77).

This manual is written for people who want to *read and write* FORTRAN 66 — to bring a vintage deck
back to life, to understand what a classic program does, or to write new code in the old style.
Every feature is shown with a small, runnable example and its result.

It is self-contained: you do not need to know any other FORTRAN to use it. It runs on
[`forterp`](../../README.md); each chapter ends with a **forterp notes** box describing anything
specific to how forterp implements that part of the language (and which knobs change it). For how
to *select and run* a dialect, see the [Python API guide](../forterp/04-running-embedding.md) and [Command-line tools](../forterp/02-cli.md).

> **FORTRAN 66 or FORTRAN 77?** F66 is the older, smaller language. If you are writing new code
> and want the `CHARACTER` type, the block `IF … THEN … ELSE … END IF`, list-directed I/O, and
> `OPEN`/`CLOSE`, you want the [FORTRAN 77 reference manual](../fortran77/README.md) instead. Use
> *this* manual for code that predates F77, or that uses the DEC FORTRAN-10 extensions.

## How to read this manual

- Chapters follow the **structure of the X3.9-1966 standard** section for section, but you can read
  them in any order — they cross-reference each other.
- Code is shown in **fixed source form** (the classic punched-card column layout explained in
  [Chapter 3](03-program-form.md)). FORTRAN 66 has **no inline comment character** (the `!` of
  later FORTRANs is a FORTRAN-10 extension), so annotations and expected results are shown on
  `C` comment lines, conventionally written `C     -> ...`.
- A box marked **forterp notes** flags behavior particular to forterp — an enforced rule, a
  supported extension, or a tunable default — including the handful of **deliberate divergences**
  forterp keeps for faithfulness to real FORTRAN-10 V5 (collected in
  [Appendix C](C-forterp-extensions.md)).
- Section numbers in parentheses, e.g. *(§6.1)*, point at the standard for authority.

## Contents

**Preliminaries**
1. [Purpose & scope](01-purpose-scope.md)
2. [Basic terminology](02-terminology.md)

**Writing a program**
3. [Program form](03-program-form.md)
4. [Data types](04-data-types.md)
5. [Data & procedure identification](05-identification.md)

**Computing**
6. [Expressions](06-expressions.md)
7. [Statements](07-statements.md)

**Program units**
8. [Procedures & subprograms](08-procedures.md)
9. [Programs](09-programs.md)
10. [Intra- & inter-program relationships](10-relationships.md)

**Appendices**
- A. [Intrinsic & basic external function reference](A-intrinsics.md)
- B. [The FORTRAN character set & collating sequence](B-character-set.md)
- C. [DEC FORTRAN-10 extensions & forterp divergences](C-forterp-extensions.md)
