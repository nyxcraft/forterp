# 10. Assignment

Assignment is how a running program stores a computed value into a variable. The form is the same
for every type — `variable = expression` — but the conversion rules differ by type *(§10)*.

## Arithmetic assignment

```fortran
      v = e
```

The expression `e` is evaluated, then **converted to the type of `v`** before being stored
*(§10.1, Table 4)*. The conversions that matter:

- **Real/double → integer truncates toward zero** (the fractional part is dropped):

  ```fortran
        I = 3.9          ! I = 3
        I = -3.9         ! I = -3   (toward zero, not -4)
  ```

- **Integer → real/double** widens exactly; **→ complex** sets the real part, imaginary 0.
- Assigning a value already of `v`'s type stores it unchanged.

Note the asymmetry with [Chapter 6](06-expressions.md): there, mixing types in an *expression*
converts up; here, the final store converts to the *target's* type, which may convert **down**
(real → integer) and lose the fraction.

## Logical assignment

```fortran
      LOGICAL FLAG
      FLAG = X .GT. 0.0        ! the relational yields a logical, stored in FLAG
```

`v` and `e` are both logical.

## Character assignment

`v` and `e` are character; they may differ in length *(§10.4)*. The value is fitted to `v`'s
declared length: a shorter value is **blank-padded on the right**, a longer one is **truncated**.

```fortran
      CHARACTER*5 S
      S = 'HI'           ! S = 'HI   '   (padded)
      S = 'HELLO!'       ! S = 'HELLO'   (truncated to 5)
```

Assigning to a **substring** changes only those character positions; the rest of the string is
untouched ([Chapter 5](05-arrays-substrings.md)):

```fortran
      S = 'ABCDE'
      S(2:4) = 'XY'      ! S = 'AXY E'  (RHS fitted to the 3-char slice)
```

## The ASSIGN statement

`ASSIGN` is a special, narrow form that stores a **statement label** (not a value) into an integer
variable, for use by an assigned `GO TO` or as a run-time format identifier *(§10.3)*:

```fortran
      ASSIGN 100 TO LBL
      GO TO LBL                ! jumps to the statement labelled 100
      ...
  100 CONTINUE
```

While a variable holds an assigned label it must not be used as an ordinary integer. `ASSIGN` and
the assigned `GO TO` are little used in new code; you will meet them in older programs
([Chapter 11](11-control.md)).

---

> **forterp notes.** Assignment conversions follow Table 4 exactly, including the truncate-toward-
> zero rule and the character pad/truncate rule. Two edges handled per the audit: assigning to a
> `PARAMETER` named constant is a hard error ([Chapter 8](08-specification.md)), and a character
> substring target outside `1 ≤ e1 ≤ e2 ≤ len` is unspecified by default / an error under
> `bounds_check` ([Chapter 5](05-arrays-substrings.md)).
