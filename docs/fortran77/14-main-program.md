# 14. Main program

The **main program** is where execution begins. Every executable program has exactly one
*(§14)*.

```fortran
      PROGRAM PAYROLL
      ...
      END
```

- The **`PROGRAM`** statement, if present, is the first statement and names the program. The name
  is documentation; it has no other use. The `PROGRAM` line is **optional** — a unit with no
  header that isn't a `FUNCTION`/`SUBROUTINE`/`BLOCK DATA` is the main program.
- A main program may contain any statements *except* `FUNCTION`, `SUBROUTINE`, `BLOCK DATA`,
  `ENTRY`, or `RETURN` — it is not a procedure and is never called.
- Reaching the main program's `END` (or executing a `STOP`) terminates the program.

That is the whole of it; the substance of a program lives in its statements (earlier chapters) and
its subprograms ([Chapter 15](15-procedures.md)).

---

> **forterp notes.** `PROGRAM` is optional and, when present, named, exactly as specified;
> execution starts at the main program's first executable statement regardless of where the unit
> appears in the source.
