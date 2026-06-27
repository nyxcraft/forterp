# 3. Source form

FORTRAN 77 source is **fixed-form**: the meaning of a line depends on which *column* a character
sits in. This is the single biggest surprise for newcomers, and the cause of most "why won't it
compile" puzzles. Once you know the column rules it is mechanical. (The layout dates from the
80-column punched card.)

## The column layout

Each line is up to 72 meaningful characters, divided into four fields *(§3.2, §3.3)*:

```
 column: 1   2   3   4   5   6   7 ............................... 72 | 73 ... 80
         └────────┬────────┘   │   └──────────────┬──────────────┘   └────┬────┘
          label field (1–5)     │       statement field (7–72)         ignored
                          continuation (6)
```

| Columns | Field | What goes there |
|---|---|---|
| **1–5** | label | an optional statement number (1–5 digits), right- or left-justified |
| **6** | continuation | blank or `0` → this is a new statement; anything else → continues the previous line |
| **7–72** | statement | the statement text itself |
| **73–80** | (ignored) | historically the card sequence number; ignored by the compiler |

So an ordinary statement starts in **column 7**:

```fortran
C234567 ← column ruler (the digit under each position)
      X = 2.0
      Y = X * X
```

## Comment lines

A line is a **comment** *(§3.2.1)* if it has `C` (or `*`) in **column 1**, or if it is entirely
blank. The whole line is ignored.

```fortran
C This whole line is a comment.
*     So is this one.

      X = 1.0          ! (the blank line above is also a comment)
```

## Continuation lines

A long statement is split by putting a **non-blank, non-`0` character in column 6** of the
following line. Columns 1–5 of a continuation must be blank. Any character will do as the
continuation mark; a digit or `&` is conventional.

```fortran
      TOTAL = A + B + C + D +
     1        E + F + G
```

The `1` in column 6 of the second line says "this is a continuation of the statement above." A
statement may have up to nineteen continuation lines.

## Statement labels

A **statement label** is 1 to 5 digits (at least one non-zero) placed in columns 1–5 *(§3.4)*. It
names a statement so other statements can refer to it — a `FORMAT` referenced by a `WRITE`, or a
target of a `GO TO` or a `DO`. Labels need not be in order or contiguous; leading zeros and blanks
within the field are not significant (`10`, `010`, and `1 0` are the same label).

```fortran
      GO TO 100
  100 CONTINUE
   10 FORMAT (I5)
```

Only labelled statements can be referred to, and a label may name at most one statement in a
program unit.

## Blanks are not significant

Outside a character constant, **blanks have no meaning** *(§3.1.6)* — they exist only to make the
source readable. This has two consequences that startle newcomers:

- **Keywords may be spaced (or not):** `GO TO`, `GOTO`, and `G O T O` are identical; so are
  `END IF` and `ENDIF`, `DOUBLE PRECISION` and `DOUBLEPRECISION`.
- **Names and numbers may contain blanks:** `N ( 1 ) = 4 2` means `N(1) = 42`, and `I N TEGER X`
  is the declaration `INTEGER X`.

```fortran
      I N TEGER N
      N ( 1 ) = 4 2          ! same as  INTEGER N  /  N(1) = 42
```

You would not normally write code this way, but it explains old listings that do — and it is why
a stray space inside a keyword never breaks anything.

## The order of statements

Within a program unit, statements must appear in a required order *(§3.5)*. The rules, simply:

1. The unit's header (`PROGRAM`, `FUNCTION`, `SUBROUTINE`, or `BLOCK DATA`) comes first, if present.
2. **`IMPLICIT`** statements come before the other specification statements.
3. All **specification** statements (type declarations, `DIMENSION`, `COMMON`, `EQUIVALENCE`,
   `PARAMETER`, `EXTERNAL`, `INTRINSIC`, `SAVE`) come before the executable statements.
4. **Statement-function** definitions come after the specifications and before the executables.
5. **Executable** statements come last, then **`END`**.
6. `FORMAT` and `ENTRY` may appear anywhere; `DATA` may appear anywhere after the specifications.

In short: *declare first, then do.* Putting a declaration after an executable statement is an
error.

## The END line

Every program unit ends with an **`END`** statement on its own initial line (no continuation).
`END` marks the physical end of the unit; in a main program it also stops execution, and in a
subprogram it acts like a `RETURN` ([Chapter 15](15-procedures.md)).

---

> **forterp notes.** forterp reads columns 7–72 as the statement and drops 73–80, exactly as
> specified, and honors blank-insignificance (the spaced examples above all run). A few latitudes:
>
> - **The order rule (point 3) is enforced under the `F77` dialect** — a specification statement
>   after an executable is a hard error. `F66`/`FORTRAN10` accept it (lenient). One consequence:
>   reusing a *type keyword* as a variable name and assigning to it after an executable (`REAL =
>   3.0`) is read as a misplaced type-statement; declare such a name up front.
> - forterp also accepts the DEC column-1 comment markers `! $ / D` in addition to `C`/`*` (a
>   superset; harmless), and does not enforce the nineteen-continuation-line limit.
> - The nineteen-line limit and the 73–80 sequence field are about the punched-card era; forterp
>   keeps the field-dropping behavior but is otherwise relaxed about line counts.
