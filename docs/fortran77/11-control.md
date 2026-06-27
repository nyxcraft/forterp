# 11. Control statements

By default a program runs straight down, one statement after the next. **Control statements**
change that — they branch, loop, call out, and stop *(§11)*. FORTRAN 77 has both the modern
structured `IF`/`DO` and the older `GO TO` forms you'll meet in vintage code.

## GO TO

**Unconditional** — jump to a labelled statement:

```fortran
      GO TO 100
      ...
  100 CONTINUE
```

**Computed `GO TO`** — pick the *i*-th label by an integer selector:

```fortran
      GO TO (10, 20, 30) K       ! K=1 -> 10, K=2 -> 20, K=3 -> 30
```

If the selector is out of range (here, not 1–3), the `GO TO` does nothing and falls through to the
next statement *(§11.2)*.

**Assigned `GO TO`** — jump to a label previously stored with `ASSIGN`
([Chapter 10](10-assignment.md)):

```fortran
      ASSIGN 200 TO LBL
      GO TO LBL
```

The computed and assigned forms are legacy; prefer the block `IF` and `DO` below.

## The arithmetic IF

A three-way branch on the **sign** of an expression *(§11.4)* — negative, zero, positive:

```fortran
      IF (X) 10, 20, 30      ! X<0 -> 10,  X=0 -> 20,  X>0 -> 30
```

Also legacy, but common in old numerical code.

## The logical IF

Run one statement when a condition is true *(§11.5)*:

```fortran
      IF (N .LT. 0) N = -N           ! a single statement after the condition
      IF (DONE) GO TO 900
```

## The block IF

The structured conditional *(§11.6–11.9)* — the workhorse of readable F77:

```fortran
      IF (K .EQ. 1) THEN
        result = 10
      ELSE IF (K .EQ. 2) THEN
        result = 20
      ELSE
        result = 30
      END IF
```

`ELSE IF` and `ELSE` are optional; you may nest block `IF`s. `END IF` may also be written `ENDIF`.

## The DO loop

A counted loop *(§11.10)*:

```fortran
      DO 10 I = 1, 10            ! I = 1, 2, ..., 10
        S = S + A(I)
   10 CONTINUE
```

- The form is `DO label var = start, stop [, step]`. The label marks the loop's last statement
  (conventionally a `CONTINUE`); the step defaults to 1 and may be negative.
- The **trip count** is computed once, up front, as `MAX(INT((stop − start + step) / step), 0)`.
  If that is zero or negative, **the loop body runs zero times** — a `DO 1 K = 5, 1` does not
  execute at all. (This *zero-trip* rule is the defining change from FORTRAN 66, whose loops always
  ran at least once.)
- After the loop, the control variable holds the value that *failed* the test — one step past the
  last used value. `DO I = 1, 10` leaves `I = 11`; a zero-trip `DO K = 5, 1` leaves `K = 5`.
- The control variable may be integer, real, or double precision.

```fortran
      M = 0
      DO 1 K = 5, 1             ! start > stop with step +1 -> zero trips
        M = M + 1
    1 CONTINUE
C     M = 0 (body never ran), K = 5
```

## CONTINUE, STOP, PAUSE, END

- **`CONTINUE`** does nothing; it is a convenient labelled placeholder, typically a `DO`
  terminator.
- **`STOP`** halts the program; an optional 1–5-digit number or character constant is displayed:
  `STOP`, `STOP 99`, `STOP 'NO DATA'`.
- **`PAUSE`** suspends until the operator resumes it (a relic of batch/interactive terminals);
  like `STOP` it may carry a number or string.
- **`END`** ends the program unit; in the main program it acts as `STOP`, in a subprogram as
  `RETURN` ([Chapter 15](15-procedures.md)).

---

> **forterp notes.** All control forms are implemented: the block `IF` family (`ENDIF` and `END
> IF`), the zero-trip `DO` with the correct post-loop control-variable value, computed-`GO TO`
> fall-through on an out-of-range selector, the arithmetic/logical/assigned forms, and
> `CONTINUE`/`STOP`/`PAUSE`/`END`. (`DO WHILE` is a DEC/Fortran-90 extension, **not** F77 — it is
> available under the `FORTRAN10` dialect, rejected under `F77`.)
