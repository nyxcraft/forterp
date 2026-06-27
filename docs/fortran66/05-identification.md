# 5. Data & procedure identification

Everything a program works on is identified by a **name** or written as a **constant** *(§5)*. This
chapter is the catalogue of those identifiers: the kinds of constant, variables, arrays and their
subscripts, and how a name acquires a data type. Two verbs recur throughout the standard:

- to **reference** a datum is to make its current value available — you reference a variable by
  using it in an expression;
- to **define** a datum is to give it a value — assignment defines a variable. A datum with no
  value yet is *undefined*, and using an undefined value is not allowed *(§10)*.

## Constants

A **constant** is a datum that is always defined and can never be redefined *(§5.1.1)*. Each data
type has its own written form (introduced in [Chapter 4](04-data-types.md)):

| Type | Example constants | Notes |
|------|-------------------|-------|
| integer | `0`, `42`, `-7` | a digit string, optionally signed *(§5.1.1.1)* |
| real | `3.14`, `.5`, `6.022E23` | decimal point and/or `E` exponent *(§5.1.1.2)* |
| double precision | `1.5D0`, `3.0D-2` | `D` exponent instead of `E` *(§5.1.1.3)* |
| complex | `(1.0,2.0)` | a parenthesized pair of reals *(§5.1.1.4)* |
| logical | `.TRUE.`, `.FALSE.` | the two truth values *(§5.1.1.5)* |
| Hollerith | `4HABCD` | count, `H`, then exactly that many characters *(§5.1.1.6)* |

A real constant is written as an integer part, a decimal point, and a fractional part — **either**
part may be empty, but **not both** *(§5.1.1.2)*: `3.`, `.5`, and `3.14` are all valid; a bare `.`
is not. A Hollerith constant may appear **only** in the argument list of a `CALL` statement and in
a `DATA` initialization statement *(§5.1.1.6)*.

## Variables and arrays

A **variable** is a datum identified by a symbolic name; it may be referenced and defined
*(§5.1.2)*. An **array** is an ordered set of data of **one, two, or three dimensions**, identified
by an array name *(§5.1.3)*; the array is declared by an array declarator (`DIMENSION`, or a type
or `COMMON` statement — [Chapter 7](07-statements.md)).

### Array elements and subscripts

A single **array element** is identified by following the array name with a parenthesized
**subscript** *(§5.1.3.1, §5.1.3.2)*. The number of subscript expressions must match the array's
declared dimensionality, and array storage is **column-major** — the first subscript varies fastest
(the *array element successor function*, §7.2.1.1.1).

Crucially, FORTRAN 66 restricts a **subscript expression** to one of just seven simple forms
*(§5.1.3.3)*, where *c* and *k* are integer constants and *v* is an integer variable:

```text
      c*v+k        c*v-k        c*v        v+k        v-k        v        k
```

```fortran
      DIMENSION A(20)
      I = 2
      A(2*I+1) = 9.0
C     -> subscript 2*I+1 = 5, a legal "c*v+k" form
```

A subscript like `A(I+J)` (two variables) or `A(I*I)` (a variable times a variable) is **not**
permitted in FORTRAN 66 — you must compute the index into an integer variable first and subscript
with that:

```fortran
      M = I + J
      A(M) = 9.0
```

## Procedures

A **procedure** is identified by a symbolic name *(§5.1.4)* and is one of: a *statement function*,
an *intrinsic function*, a *basic external function*, an *external function*, or an *external
subroutine* (all in [Chapter 8](08-procedures.md)). A **function** supplies a result to be used at
the point of reference; a **subroutine** does not — it is invoked by `CALL` and acts through its
arguments and side effects.

A **function reference** is the function name followed by an actual argument list in parentheses
*(§5.2)*: `SQRT(X)`, `MAX0(I,J,K)`.

## Type rules

The data type of a name is fixed within a program unit *(§5.3)*:

- a **constant**'s type is implicit in how it is written;
- a **subroutine** or **common block** name has no data type;
- a **variable, array, or statement-function** name takes its type from an explicit type-statement
  if present; otherwise by the **implicit rule** — initial letter `I, J, K, L, M, N` → integer, any
  other letter → real;
- an **intrinsic** or **basic external** function has the type given in Tables 3 and 4
  ([Appendix A](A-intrinsics.md));
- an **external function**'s type is set in its own subprogram (implicitly by name, or explicitly
  on the `FUNCTION` statement).

## Dummy arguments

A **dummy argument** of an external procedure identifies a variable, array, subroutine, or external
function *(§5.4)*. When the procedure is referenced, each dummy is associated with the corresponding
actual argument; a value of the same type must be available through that association. Argument
association is detailed in Chapters [8](08-procedures.md) and [10](10-relationships.md).

> **forterp notes.**
>
> - forterp **enforces the restricted subscript forms** under `F66`: a subscript outside the seven
>   shapes of §5.1.3.3 (plus their obvious commutations, e.g. `I*2` and `2+I`) is a hard error
>   (`?FTNNRC … F66 array subscript must be of the form …`). The `FORTRAN10` and `F77` dialects lift
>   this and allow a general integer expression as a subscript.
> - forterp allows arrays of up to **seven** dimensions on every dialect; the X3.9-1966 limit of
>   **three** is not enforced, as accepting more cannot break a conforming program. (The cap of
>   seven *is* enforced — see the [F77 manual](../fortran77/05-arrays-substrings.md).)
