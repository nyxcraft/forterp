# 17. Storage association & definition

This chapter is the formal model behind two things you have already used: making names **share
storage** (`COMMON`, `EQUIVALENCE`, arguments), and the idea that a variable may be **defined** or
**undefined** *(§17)*. You can write plenty of F77 without reading it; come here when sharing or
initialization behaves in a way you want to understand exactly.

## The storage sequence

The standard models memory as a **storage sequence** of *storage units* *(§17.1, §2.13)*:

- integer, real, logical → **one** numeric storage unit each,
- double precision, complex → **two** numeric storage units each,
- character of length *n* → **n** character storage units.

Numeric and character units are different kinds and never associate with each other.

## Association: when two names share storage

Two storage sequences are **associated** when they occupy the same memory *(§17.1.2)*. F77 creates
association four ways:

- **`COMMON`** — units lay their variables onto a shared block, matched by position
  ([Chapter 8](08-specification.md)).
- **`EQUIVALENCE`** — two names in one unit name the same storage
  ([Chapter 8](08-specification.md)).
- **Argument association** — a dummy argument names the actual argument's storage
  ([Chapter 15](15-procedures.md)).
- **`ENTRY`** — entry points share the host's storage.

**Total** association is when the sequences line up exactly; **partial** association is a partial
overlap (only allowed between character entities, or between a double/complex entity and the
numeric units it spans). The classic overlay:

```fortran
      REAL    A(4)
      INTEGER B(4)
      EQUIVALENCE (A, B)        ! A(i) and B(i) are the same storage, viewed two ways
```

No conversion happens — the *bits* are shared and reinterpreted by each name's type.

## Definition status

At any moment a variable is either **defined** (holds a usable value) or **undefined**. The
standard says a reference to an undefined entity has **"no predictable value"** *(§17.1)* — so a
correct program always defines a variable before it reads it.

What **defines** a variable *(§17.2)*: assignment, reading into it, a `DATA` initialization, being
a `DO` variable, `ASSIGN`, or association with something already defined.

What leaves a variable **undefined** *(§17.3)*: it starts undefined at program start (unless
`DATA`-initialized); a non-`SAVE` local becomes undefined after `RETURN`/`END`; defining one entity
of an associated pair of *different* type undefines the other; and a few I/O and skipped-function
cases.

The practical upshot is two habits:

- **Initialize before you use** (with `DATA` or an assignment).
- **Use `SAVE`** if a local must keep its value across calls ([Chapter 8](08-specification.md)) —
  without it, the standard does not promise the value survives a `RETURN`.

---

> **forterp notes.**
> - **Storage units:** forterp uses one *value slot* per element. `COMPLEX` correctly occupies two
>   slots, but `DOUBLE PRECISION` occupies one (not two numeric units). This is observable only in
>   the rare partial-association overlay of a double against a pair of reals; the **`PDP10`** target
>   is faithful to the two-word model. (This — and the NATIVE `REAL`≡`DOUBLE` precision of
>   [Chapter 4](04-data-types.md) — is the one divergence that can affect a conforming program; see
>   [Appendix D](D-forterp-extensions.md).)
> - **Definition status is not tracked:** forterp does not trap a read of an undefined entity, and
>   its locals happen to be static (persist across calls). Both are within the "no predictable
>   value" latitude and never affect a conforming program — but because they are *undefined*
>   behavior, the exact result is unspecified and may change; rely on `DATA`/assignment and `SAVE`,
>   not on what forterp happens to do.
