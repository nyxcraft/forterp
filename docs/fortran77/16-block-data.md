# 16. Block data

A **block data** subprogram exists for one purpose: to give **initial values to named `COMMON`
blocks** *(§16)*. It is the only place a named common block may be initialized — a `DATA` statement
in a main program or ordinary subprogram cannot touch common.

```fortran
      BLOCK DATA TABLES
      COMMON /PHYS/ G, C
      DATA   G, C /9.81, 2.998E8/
      END
```

- Begins with **`BLOCK DATA`**, optionally named (`BLOCK DATA TABLES`). The name, if given, must
  be unique across the program.
- It is **nonexecutable** — it contains only specification statements: `IMPLICIT`, `PARAMETER`,
  `DIMENSION`, `COMMON`, `SAVE`, `EQUIVALENCE`, type statements, and `DATA`. No executable code.
- Only **named** common may be initialized here (not blank common).
- A program may have several block data subprograms, but a given common block may be initialized
  in only one of them.

The main program (and any subprogram) then declares the same `COMMON` block and sees the initial
values:

```fortran
      PROGRAM SIM
      COMMON /PHYS/ G, C        ! G and C already hold 9.81 and 2.998E8
      ...
      END
```

Two finer rules *(§16.2)*: if you initialize *any* entity of a common block, the block data should
list **all** of the block's entities (so its full layout is established); and a program may contain
**at most one *unnamed*** block data subprogram.

---

> **forterp notes.** A `BLOCK DATA` correctly seeds named common read by other units. The
> **at-most-one-unnamed** rule *is enforced* — a second unnamed `BLOCK DATA` is a hard error
> (otherwise the two would collide and one block's initialization would be silently lost). The
> "specify all entities" rule is *not* enforced: a block data may initialize just a prefix of a
> block (harmless; the rest stays uninitialized). Note `BLOCK DATA` is obsolescent in modern
> Fortran (replaced by module initialization), but it is the standard mechanism in F77. See
> [Appendix D](D-forterp-extensions.md).
