# 9. Programs

This short chapter assembles the pieces from the previous chapters into a whole **executable
program** and describes the order in which its statements run *(§9)*.

## What a program is made of

An **executable program** is a collection of statements, comment lines, and end lines that
completely describes a computing procedure *(§9.1)*. Its anatomy, from the inside out:

- A **program part** is the run of statements containing at least one executable statement (and
  optionally `FORMAT` and `DATA` statements), possibly preceded by statement function definitions
  *(§9.1.1)*.
- A **program body** is the specification statements and/or `FORMAT` statements, followed by the
  program part, followed by an **end line** *(§9.1.2)*.
- A **main program** is simply a program body *(§9.1.5)* — the one unit not headed by `FUNCTION`,
  `SUBROUTINE`, or `BLOCK DATA`.
- A **subprogram** is a `SUBROUTINE` or `FUNCTION` unit (a program body with a heading), or a
  `BLOCK DATA` unit *(§9.1.3, §9.1.4)*.
- An **executable program** is **one main program plus any number of subprograms** *(§9.1.6)*.

```fortran
      PROGRAM AREA
      READ (5,100) R
100   FORMAT (F10.0)
      A = PI(R)
      WRITE (6,200) A
200   FORMAT (1X, F12.4)
      STOP
      END
C
      FUNCTION PI(R)
      PI = 3.14159 * R * R
      RETURN
      END
```

Here the main program `AREA` and the function subprogram `PI` together make one executable program.
Each unit ends with its own `END` line.

## How a program runs

Execution begins with the **first executable statement of the main program** *(§9.2)*. From there,
statements run in the order written, **except** when a statement explicitly redirects the flow:

- a `GO TO`, an arithmetic `IF`, a `RETURN`, or a `STOP`;
- reaching the terminal statement of a `DO` (which may loop back).

A subprogram, when referenced, starts at *its* first executable statement and runs the same way
until a `RETURN` sends control back to the caller. Nonexecutable statements (`FORMAT`, `DIMENSION`,
`DATA`, …) are never "run" — they are in effect throughout, but the flow of control passes around
them.

> **forterp notes.** forterp finds the main program structurally — the unit that is not a
> `FUNCTION`, `SUBROUTINE`, or `BLOCK DATA` — so a leading `PROGRAM` statement is optional. It
> begins execution at that unit's first executable statement, exactly as §9.2 prescribes, and the
> units of a multi-file program are linked first (see [Command-line tools](../forterp/02-cli.md)).
