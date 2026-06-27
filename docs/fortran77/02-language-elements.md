# 2. Language elements & concepts

This chapter is the vocabulary of the language: the characters you write with, the names you give
things, the kinds of data you can hold, and a few ideas (storage, association) that the later
chapters lean on. It is a map — each topic links to the chapter that covers it in full.

## The character set

A FORTRAN 77 program is written with 49 characters *(§3.1)*:

- the 26 **letters** `A`–`Z` (FORTRAN 77 is written in upper case),
- the 10 **digits** `0`–`9`,
- the **blank**, and
- 12 **special characters**: `= + - * / ( ) , . $ '` and the colon `:`.

Any other character (lower case, `#`, `@`, …) may appear only inside a character or Hollerith
constant. The blank is not significant outside character context — see
[Chapter 3](03-source-form.md), where `GO TO` and `GOTO` turn out to be the same thing.

## Symbolic names

A **symbolic name** identifies a variable, array, function, common block, and so on. The rules
*(§2.2)* are simple:

- 1 to 6 characters,
- each a letter or a digit,
- the first a **letter**.

So `X`, `N`, `SUM`, `A1`, `MATRIX` are valid; `2NDVAL` (starts with a digit) and `LONGNAME`
(seven characters) are not.

**There are no reserved words.** `IF`, `DO`, `REAL`, `INDEX`, `SUM` are keywords or intrinsic
functions, but you may also use them as your own variable names — the compiler tells which is
which from context. Using an intrinsic name as a variable is common and well-defined: in a unit
where you write `INTEGER INDEX` and assign to `INDEX`, it is your variable, not the `INDEX`
function.

```fortran
      INTEGER INDEX, SUM
      INDEX = 5
      SUM   = 10
      ...                       ! INDEX and SUM are ordinary variables here
```

## The six data types

Every datum has one of six types. You will meet them in full in [Chapter 4](04-data-types.md);
here they are at a glance:

| Type | Holds | Example constant | Declared with |
|---|---|---|---|
| **INTEGER** | a whole number | `42`, `-7` | `INTEGER` |
| **REAL** | a single-precision floating-point number | `3.14`, `5.0E3` | `REAL` |
| **DOUBLE PRECISION** | a higher-precision float | `2.0D0` | `DOUBLE PRECISION` |
| **COMPLEX** | a pair (real, imaginary) | `(1.0, 2.0)` | `COMPLEX` |
| **LOGICAL** | a truth value | `.TRUE.`, `.FALSE.` | `LOGICAL` |
| **CHARACTER** | a fixed-length string | `'HELLO'` | `CHARACTER` |

A name acquires a type in one of three ways, in order of authority: an explicit type-statement
(`REAL X`), an `IMPLICIT` rule, or — failing both — the **implicit default**: a name beginning
with `I, J, K, L, M, N` is `INTEGER`; any other initial letter is `REAL` *(§4.1.2)*. (Mnemonic:
`I`–`N` is the integer range, after the first two letters of *integer*.) This default is why so
much classic code uses `I, J, K` for loop counters and `N` for counts without declaring them.

## Constants, variables, arrays, and substrings

- A **constant** is a fixed value written literally (`42`, `'HELLO'`). Constant forms are in
  [Chapter 4](04-data-types.md). You can also give a constant a name with `PARAMETER`
  ([Chapter 8](08-specification.md)).
- A **variable** is a single named datum you can assign to.
- An **array** is a named, rectangular collection of elements of one type, addressed by
  subscripts — `A(3)`, `M(I,J)` ([Chapter 5](05-arrays-substrings.md)).
- A **substring** is a contiguous slice of a character datum — `S(2:4)`
  ([Chapter 5](05-arrays-substrings.md)).

## Statements and lines

A program is a sequence of **statements**. Most occupy one line, but a long statement may be
**continued** across several lines, and a line may be a comment. The column layout that
distinguishes an initial line, a continuation, a label, and a comment is the subject of
[Chapter 3](03-source-form.md).

Statements come in two broad classes *(§7)*:

- **Executable** statements *do* something when the program runs (assignment, `IF`, `DO`, `CALL`,
  `READ`/`WRITE`, `GO TO`, …).
- **Nonexecutable** statements *describe* the program (type declarations, `DIMENSION`, `COMMON`,
  `PARAMETER`, `DATA`, `FORMAT`, `IMPLICIT`, …). They take effect at compile time and have a
  required position relative to the executable statements ([Chapter 7](07-statements.md)).

## Storage and association (a preview)

The standard describes memory as a **storage sequence** of *storage units*. Integer, real, and
logical each occupy one *numeric storage unit*; double precision and complex occupy two; a
character of length *n* occupies *n* *character storage units*. Numeric and character units are
different kinds and never overlap *(§2.13)*.

You usually don't think about this — until two names are made to **share** storage. That happens
with `COMMON` (sharing data across program units), `EQUIVALENCE` (two names for the same storage
in one unit), or **argument association** (a dummy argument naming the actual you passed). The
full model — and what it means for a value to be *defined* or *undefined* — is
[Chapter 17](17-association.md).

---

> **forterp notes.** **No reserved words** is honored: forterp resolves keyword-versus-name by
> context, so an intrinsic name used as a variable (the common case) works. The one rough edge is
> a *type keyword* reused as a variable and **assigned after an executable statement** (e.g.
> `REAL = 3.0` following an assignment) — forterp reads the leading `REAL` as a type-statement and
> reports it out of order; declare such a variable up front, or simply avoid naming a variable
> after a type keyword.
>
> **Name length:** the standard caps names at six characters. forterp accepts a longer name
> (keeping the first six significant) rather than rejecting it; it never matters for conforming
> code, which has no names over six characters. Implicit typing (`I`–`N` ⇒ integer) is the default
> exactly as specified.
