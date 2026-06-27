# 7. Statements at a glance

This short chapter is a map of the statement set. FORTRAN 77 divides statements into two classes
*(§7)* — **executable** (they act when the program runs) and **nonexecutable** (they describe the
program to the compiler). Knowing which is which explains the ordering rule from
[Chapter 3](03-source-form.md): all the describing comes before the doing.

## Nonexecutable statements

These define data, types, and layout. They take effect at compile time; they are never "run."

| Statement | Purpose | Chapter |
|---|---|---|
| `PROGRAM`, `FUNCTION`, `SUBROUTINE`, `BLOCK DATA` | program-unit headers | [14](14-main-program.md), [15](15-procedures.md), [16](16-block-data.md) |
| `IMPLICIT` | set default types by initial letter | [8](08-specification.md) |
| `INTEGER`, `REAL`, `DOUBLE PRECISION`, `COMPLEX`, `LOGICAL`, `CHARACTER` | type declarations | [8](08-specification.md) |
| `DIMENSION` | array shapes | [8](08-specification.md) |
| `COMMON` | shared storage across units | [8](08-specification.md) |
| `EQUIVALENCE` | two names for one storage | [8](08-specification.md) |
| `PARAMETER` | named constants | [8](08-specification.md) |
| `EXTERNAL`, `INTRINSIC` | declare procedure names | [8](08-specification.md) |
| `SAVE` | retain locals across calls | [8](08-specification.md) |
| `DATA` | compile-time initial values | [9](09-data.md) |
| `FORMAT` | I/O layout (referenced by label) | [13](13-format.md) |
| `ENTRY` | extra entry points in a subprogram | [15](15-procedures.md) |
| `END` | physical end of a program unit | [3](03-source-form.md) |

## Executable statements

These do the work, in flow order.

| Group | Statements | Chapter |
|---|---|---|
| Assignment | `v = e`, `ASSIGN s TO i` | [10](10-assignment.md) |
| Control | `GO TO`, arithmetic/logical/block `IF`, `DO`, `CONTINUE`, `STOP`, `PAUSE`, `END` | [11](11-control.md) |
| Procedure | `CALL`, `RETURN` | [15](15-procedures.md) |
| Input/output | `READ`, `WRITE`, `PRINT`, `OPEN`, `CLOSE`, `INQUIRE`, `BACKSPACE`, `ENDFILE`, `REWIND` | [12](12-io.md) |

## The order, once more

Within a program unit: header → `IMPLICIT` → other specifications → statement-function definitions
→ executable statements → `END`. `FORMAT` and `ENTRY` may appear anywhere; `DATA` may appear
anywhere after the specifications. (Full rule: [Chapter 3](03-source-form.md).)

---

> **forterp notes.** The full F77 statement set is implemented. The ordering rule (specifications
> before executables) is enforced under the `F77` dialect; see [Chapter 3](03-source-form.md).
