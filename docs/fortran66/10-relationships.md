# 10. Intra- & inter-program relationships

This final language chapter is the standard's formal model: how a **symbolic name** is classified,
what it means for a datum to be **defined**, and the three ways entities come to **share** a value
or storage *(§10)*. You rarely need to recite these rules, but they explain *why* the earlier rules
are what they are.

## Classes of symbolic name

Within a program unit, every symbolic name belongs to exactly one **class** *(§10.1)*:

| Class | What the name identifies |
|-------|--------------------------|
| I | an array (and its elements) |
| II | a variable |
| III | a statement function |
| IV | an intrinsic function |
| V | an external function |
| VI | a subroutine |
| VII | an external procedure that can't be classified as V or VI here |
| VIII | a common block name |

A name's class is fixed by how it is used *(§10.1.1)*. For example, a name is a **variable**
(Class II) if it is never immediately followed by `(`, unless that `(` is in a `FUNCTION` heading
*(§10.1.9)*; it is a **statement function** (Class III) if it is defined by a statement function and
every use is followed by `(` *(§10.1.6)*; it is an **intrinsic function** (Class IV) if it matches a
Table 3 name used as a function *(§10.1.7)*. Once a name is used as an external function, subroutine,
or block name (Class V, VI, VII, VIII) anywhere in an executable program, no other unit may use that
name for anything else *(§10.1.1)*.

A consequence worth remembering: because a common block name (Class VIII) and an array name
(Class I) are separate classes, the *same* identifier may name both a common block and a variable in
one unit — `COMMON /X/ X` is legal, the block `/X/` and the variable `X` being distinct.

## Definition and undefinition

An entity is **defined** when it has a predictable value and **undefined** otherwise; referencing an
undefined entity is not allowed *(§10.2)*. The standard distinguishes **two levels** of definition:

- **first-level** definition applies to array elements and to real, double precision, complex, and
  logical variables;
- **second-level** definition adds the stricter guarantee needed for **integer** variables that are
  used as **subscripts** or as **`DO` parameters** *(§10.2)*.

A variable becomes defined by being assigned, by being read into, or by `DATA`/`BLOCK DATA`
initialization. It can become *undefined* again — most notably, the control variable of a `DO`
becomes undefined when the loop finishes by satisfying its limit *(§7.1.2.8.1)*. The practical rule
is simple: **give a variable a value before you use it.**

## Associations that share a value

Three mechanisms make two or more entities refer to the same value or storage; defining one then
defines (or undefines) all of them *(§10.2.2)*:

1. **COMMON association** — entities in corresponding positions of a common block, across program
   units ([Chapter 7](07-statements.md));
2. **EQUIVALENCE association** — entities listed together in an `EQUIVALENCE`, within one unit;
3. **argument substitution** — a dummy argument associated with its actual argument when a procedure
   is referenced ([Chapter 8](08-procedures.md)).

When entities are associated, they should be used at the **same type**: if an entity of one type
becomes defined, all associated entities of a *different* type become **undefined** *(§10.2.2)*.
Reading an integer through a common slot last written as a real, for instance, is undefined.

```fortran
      DIMENSION A(2,2), B(4)
      EQUIVALENCE (A, B)
C     -> A and B share storage; defining B(1) defines A(1,1) (same type, OK)
```

> **forterp notes.**
>
> - forterp does not police every definition rule at runtime — using an **undefined** variable
>   generally reads whatever the storage holds rather than raising an error, matching how real
>   FORTRAN-10 behaved. The one place forterp is deliberately *more* defined than the standard is an
>   out-of-bounds array read, which yields `0` rather than undefined behavior — see
>   [Appendix C](C-forterp-extensions.md).
> - **Mixing types through `EQUIVALENCE` or `COMMON`** (the §10.2.2 "different type → undefined"
>   case) is where the value model matters: forterp reinterprets the underlying word, and what you
>   get depends on the [target](C-forterp-extensions.md) (`NATIVE` 64-bit vs `PDP10` 36-bit). Keep
>   associated entities to one type for portable results.
