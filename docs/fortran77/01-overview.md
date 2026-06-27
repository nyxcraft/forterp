# 1. Overview & program structure

FORTRAN 77 is a language for numerical and scientific computing, standardized as ANSI X3.9-1978.
It is compact and close to the machine of its era: fixed-format source, a handful of data types,
arrays, and a rich formatted-I/O system. This chapter shows you a whole program, names its parts,
and explains how it runs — the details of each part follow in later chapters.

## Your first program

```fortran
      PROGRAM AREA
C     Area of a circle of radius 2.
      REAL R, A
      R = 2.0
      A = 3.14159 * R * R
      WRITE (6, 10) R, A
   10 FORMAT (' radius =', F5.2, '   area =', F7.3)
      END
```

Running it prints:

```
 radius = 2.00   area = 12.566
```

Reading it top to bottom:

- **`PROGRAM AREA`** names the main program. The name is for your benefit; it is optional (a
  program with no `PROGRAM` line is still a valid main program).
- **`C` in column 1** marks a comment line — the whole line is ignored.
- **`REAL R, A`** is a *declaration*: it tells the compiler that `R` and `A` hold real
  (floating-point) numbers. Declarations describe data; they do not do anything when the program
  runs.
- **`R = 2.0`** and **`A = 3.14159 * R * R`** are *assignments* — they compute a value and store
  it in a variable. These are *executable* statements: they happen, in order, when the program
  runs.
- **`WRITE (6, 10) R, A`** sends `R` and `A` to output unit 6 (the standard output), formatted
  according to the `FORMAT` statement labelled `10`.
- **`10 FORMAT (...)`** describes how the numbers are laid out as text. `F5.2` means "a real
  number in a 5-character field with 2 decimals"; the quoted pieces are printed literally. The
  `10` in columns 1–5 is its *statement label*, referenced by the `WRITE`.
- **`END`** marks the physical end of the program unit. Reaching `END` in a main program stops the
  program.

Notice the indentation: real code starts in **column 7**. The first six columns are reserved (for
comment markers, statement labels, and line continuation). That fixed layout is the one quirk
that surprises newcomers; [Chapter 3](03-source-form.md) covers it fully. For now, just start each
statement at column 7 and put any label in columns 1–5.

## What a program is made of

A complete FORTRAN program is one **executable program**, built from one or more **program
units**. There are four kinds:

| Program unit | Purpose | Begins with |
|---|---|---|
| **Main program** | where execution starts; exactly one per program | `PROGRAM` (optional) |
| **Subroutine** | a reusable action, invoked with `CALL` | `SUBROUTINE` |
| **Function** | a reusable computation that returns a value, used in an expression | `[type] FUNCTION` |
| **Block data** | supplies initial values for `COMMON` blocks; does nothing at run time | `BLOCK DATA` |

Subroutines and functions are collectively called **subprograms** or **procedures**. Here is a
program with a function alongside the main program:

```fortran
      PROGRAM SQ
      INTEGER N
      N = ISQ(7)
      WRITE (6, *) N
      END

      INTEGER FUNCTION ISQ(K)
      ISQ = K * K
      RETURN
      END
```
→ prints ` 49`. (`WRITE (6, *)` is *list-directed* output — "format it sensibly for me"; see
[Chapter 12](12-io.md).)

Each program unit is independent: it has its own variables and its own statement labels. Units
share data only through argument lists ([Chapter 15](15-procedures.md)) or `COMMON`
([Chapter 8](08-specification.md)). The program units may appear in any order in the source; the
one that *runs first* is always the main program, regardless of where it sits.

## How a program runs

Execution begins at the **first executable statement of the main program** and proceeds one
statement after another, in source order, until something redirects it:

- a control statement (`GO TO`, an `IF`, a `DO` loop — [Chapter 11](11-control.md)) jumps or
  loops,
- a `CALL` or function reference runs a subprogram and returns,
- `STOP` (or reaching the main program's `END`) ends the program.

Nonexecutable statements — declarations, `FORMAT`, `DATA`, `PARAMETER`, and so on — are not
"reached" in this flow; they inform the compiler and may appear before the executable statements
(the exact ordering rules are in [Chapter 7](07-statements.md)).

## Running these examples

Every example in this manual runs on forterp. The shortest way:

```python
import forterp
forterp.run_source(src, dialect=forterp.F77, printer=print)
```

or from the command line, `forterp --std f77 prog.for`. See the
[forterp F77 guide](../FORTRAN77.md) for the dialect switches, targets, and tunable knobs.

---

> **forterp notes.** forterp implements the **full** F77 language (not the subset level). The F77
> dialect is one of three forterp offers — `F66` (the 1966 base), `FORTRAN10` (the DEC FORTRAN-10
> superset), and `F77` — selected with `dialect=forterp.F77`. Standard output (unit 6) defaults to
> a *terminal* model under F77, matching modern compilers; the classic line-printer carriage
> control is the default under `F66`/`FORTRAN10` and is tunable (see [Chapter 13](13-format.md)).
> Where a program does something the standard prohibits, forterp's response is described in the
> relevant chapter's notes and summarized in [Appendix D](D-forterp-extensions.md).
