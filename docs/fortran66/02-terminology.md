# 2. Basic terminology

This chapter introduces the words the rest of the manual leans on *(§2)*. They form a small
vocabulary for talking about the *parts* of a FORTRAN program. None of it is code you write; it is
the scaffolding the standard uses to describe what you write.

## Programs and program units

An **executable program** is a self-contained computing procedure *(§9.1.6)*. It consists of
**precisely one main program** and, optionally, one or more **subprograms**.

- A **main program** is a set of statements and comments that does *not* begin with a `FUNCTION`,
  `SUBROUTINE`, or `BLOCK DATA` statement *(§9.1.5)*. Every executable program has exactly one.
- A **subprogram** is a unit that *is* headed by one of those statements:
  - one headed by `FUNCTION` or `SUBROUTINE` is a **procedure subprogram** — it specifies actions
    (a computation, a side effect);
  - one headed by `BLOCK DATA` is a **specification subprogram** — it only supplies initial values
    to named common, and specifies nothing to execute.

The umbrella term **program unit** means *either* a main program *or* a subprogram. A program unit
that another unit can invoke is an **external procedure**: a `FUNCTION` subprogram is referenced as
a **function** (it returns a value into an expression), a `SUBROUTINE` subprogram is invoked by a
`CALL` statement.

```fortran
      PROGRAM MAIN
      X = SQ(3.0)
C     -> references the function SQ
      CALL SHOW(X)
C     -> invokes the subroutine SHOW; prints "  9.00"
      STOP
      END
C
C     a procedure subprogram (function)
      FUNCTION SQ(A)
      SQ = A*A
      RETURN
      END
C
C     a procedure subprogram (subroutine)
      SUBROUTINE SHOW(V)
      WRITE(6,100) V
100   FORMAT(1X,F6.2)
      RETURN
      END
```

Chapters [8](08-procedures.md) and [9](09-programs.md) cover procedures and the make-up of a
complete program in full; here we only need the names.

## Lines, statements, and comments

A program unit is built from **lines**. A **statement** is written on one or more lines: the first
is the **initial line** and any others are **continuation lines** *(§3.2)*. A third kind of line, a
**comment line**, is not part of any statement — it exists purely to document the program for a
human reader.

Statements fall into two broad classes *(§7.1, §7.2)*:

- **executable statements** specify *action* — an assignment, a jump, a `CALL`, an I/O operation;
- **nonexecutable statements** describe the program rather than act: they declare the
  characteristics of data (`DIMENSION`, `COMMON`, type-statements), supply editing information
  (`FORMAT`), define statement functions, or arrange data (`DATA`).

The exact column layout that distinguishes an initial line from a continuation or a comment is the
subject of [Chapter 3](03-program-form.md).

## Names, operators, and lists

The syntactic pieces of a statement are **names** and **operators** *(§5)*. Names identify the
things a program works on — data (variables, arrays, constants) and procedures. Operators (`+`,
`*`, `.AND.`, and the imperative verbs like `GO TO`) specify the action taken on what the names
identify.

One kind of name is worth singling out now: an **array name**. An array is a named, ordered
collection of data declared in an *array declarator* *(§7.2.1.1)*; a single element is identified
by qualifying the array name with a **subscript** *(§5.1.3)*, as in `A(2,3)`. Arrays are the
subject of much of [Chapter 7](07-statements.md).

Throughout the standard (and this manual) a **list** is a sequence of items separated by commas —
a subscript list `(I,J)`, an I/O list, a `COMMON` list. The standard notes that such a list must
contain at least one item unless an exception is stated *(§2)*.

> **forterp notes.** forterp builds an executable program from one *or more* source files: you can
> keep the main program and each subprogram in separate files and forterp links them, the way a
> classic `LINK`/`LOADER` step would (see [CLI.md](../CLI.md) for multi-file runs). The main
> program is identified structurally — the unit that is not headed by `FUNCTION`, `SUBROUTINE`, or
> `BLOCK DATA` — exactly as in §9.1.5, so a leading `PROGRAM` statement is convenient but not
> required for forterp to find it.
