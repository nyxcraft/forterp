# 18. Scopes & symbolic names

The last formal chapter answers: *where is a name known, and what does it mean?* FORTRAN 77's
scoping is simple — there are no nested procedures and no blocks — so a name is either **global**
(known across the whole program) or **local** (known in one program unit) *(§18)*.

## Global vs local

**Global** entities are known throughout the executable program, and their names must be unique
across it *(§18.1.1)*:

- common-block names,
- external function and subroutine names,
- the main program name and block-data names.

**Local** entities belong to a single program unit; the *same* name may mean different things in
different units *(§18.1.2)*:

- variables, arrays, named constants (`PARAMETER`),
- statement functions, intrinsic functions, dummy procedures.

So `X` in one subroutine and `X` in another are unrelated variables; they share data only through
arguments or `COMMON`. A few names have an even narrower scope: a statement function's dummy
arguments, and a `DATA` implied-DO variable, are local to that one statement.

## Classes, and "no reserved words"

Because FORTRAN has no reserved words, the compiler decides what a name *is* — its **class** — from
context *(§18.2)*. The same spelling can be a keyword in one place and your variable in another:

```fortran
      INTEGER INDEX            ! INDEX is now this unit's variable...
      INDEX = 5
      K = INDEX(STR, 'X')      ! ...and INDEX the intrinsic elsewhere is a different unit's affair
```

The resolution rules, informally:

- A name followed by `(` in an expression is a function reference or an array element — decided by
  whether the name was declared an array.
- An intrinsic-function name can be shadowed by a dummy argument, a declared variable, or an
  `EXTERNAL`/`INTRINSIC` declaration.
- A common-block name (it lives in `/…/`) may also be used as a local variable or array name —
  they don't collide.
- A function's own name doubles as the result variable inside the function
  ([Chapter 15](15-procedures.md)).

The one firm rule: **a name must not belong to two local classes in the same unit** — you cannot
use `FOO` as both a variable and a statement function, or assign to a `PARAMETER` constant.

---

> **forterp notes.** forterp resolves name classes by context exactly this way (no reserved
> words), so an intrinsic name used as a variable — the common case — works, and is exercised
> throughout the conformance corpus. The general "one name, one local class" prohibition is not
> comprehensively diagnosed (a conforming program never violates it), but its one common, harmful
> instance — **assigning to a `PARAMETER`** — is a hard error rather than a silently-dropped
> assignment ([Chapter 8](08-specification.md)). Names longer than six characters are accepted
> (first six significant) rather than rejected; see [Appendix D](D-forterp-extensions.md).
