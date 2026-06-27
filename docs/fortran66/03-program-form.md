# 3. Program form

FORTRAN 66 was written for the **punched card**, and its physical form still reflects that: a
program is a sequence of 72-column lines, and a few specific columns carry special meaning. This
chapter covers the character set a program is written in *(§3.1)*, the column layout of a line
*(§3.2)*, how lines group into statements *(§3.3)*, statement labels *(§3.4)*, and the rules for
symbolic names *(§3.5)*.

## The FORTRAN character set

A program is written using just **49 characters** *(§3.1)*: the 26 letters `A–Z`, the ten digits
`0–9`, the **blank**, and twelve special characters:

| Char | Name | Char | Name |
|------|------|------|------|
| (blank) | blank | `(` | left parenthesis |
| `=` | equals | `)` | right parenthesis |
| `+` | plus | `,` | comma |
| `-` | minus | `.` | decimal point |
| `*` | asterisk | `$` | currency symbol |
| `/` | slash | | |

Digits are decimal *(§3.1.1)*, except inside a `STOP` or `PAUSE` statement, where a string of
digits is read as **octal**. The blank character has no meaning except in a few specified places
(and inside Hollerith data); elsewhere you may use blanks freely to make a program readable
*(§3.1.4.1)*. The order in which the characters are listed above does **not** imply a collating
sequence *(§3.1)* — for that, see [Appendix B](B-character-set.md).

## Lines and columns

A **line** is up to 72 characters from the character set *(§3.2)*. The character positions are
**columns**, numbered 1 to 72 from the left. Each column range has a job:

```text
 column:  1         2 ... 5   6        7 ....................... 72
          +---------+---------+-+------------------------------------+
          | C = comment       | |  the statement text                |
          | or statement label| |  (continuation mark in column 6)   |
          +-------------------+-+------------------------------------+
```

- **Comment line** — a `C` in **column 1** marks the whole line as a comment *(§3.2.1)*. It
  documents the program and is otherwise ignored.
- **End line** — a line blank in columns 1–6 with the letters `E`, `N`, `D` in that order in
  columns 7–72 *(§3.2.2)*. Every program unit must physically end with one.
- **Initial line** — the first line of a statement: not a comment or end line, with a `0` or blank
  in **column 6** *(§3.2.3)*. Columns 1–5 hold the statement label (or are blank).
- **Continuation line** — any character *other than* `0` or blank in **column 6** (and not a `C` in
  column 1) continues the previous statement *(§3.2.4)*.

```fortran
C     THIS IS A COMMENT LINE
      X = 1.0 + 2.0 + 3.0 +
     1    4.0 + 5.0
C     -> the "1" in column 6 continues the statement; X = 15.0
```

## Statements

A **statement** occupies columns 7–72 of an initial line, optionally followed by up to **nineteen
continuation lines** *(§3.3)* — so a single statement spans at most twenty lines. The text is read
by concatenating columns 7–72 of the initial line, then of each continuation line in turn.

## Statement labels

A statement may be **labeled** so other statements can refer to it *(§3.4)*. A label is one to five
digits placed anywhere in columns 1–5; its numeric value is not significant but must be **greater
than zero**, and leading zeros do not distinguish labels (`010` and `10` are the same label). No
two statements in a program unit may carry the same label.

```fortran
      GO TO 10
      X = 1.0
C     -> skipped
10    X = 2.0
C     -> label 10 is the GO TO target; X = 2.0
```

## Symbolic names

A **symbolic name** is one to six **alphanumeric** characters, the first of which must be a
**letter** *(§3.5)*: `X`, `A1`, `MASS`, `VALUE2`. Names identify variables, arrays, functions,
subroutines, and common blocks; the rules for what a name *means* in each context are in
[Chapter 5](05-identification.md) and [Chapter 10](10-relationships.md).

> **forterp notes.**
>
> - forterp reads classic fixed-form source: column 1 `C` comments, the column-6 continuation
>   mark, labels in columns 1–5, and **columns past 72 are ignored** (the old "identification
>   field" that held card sequence numbers). You can therefore paste real 80-column card images
>   and the sequence numbers in columns 73–80 are harmless.
> - For input typed at a terminal rather than punched, forterp also accepts free CR/LF lines and
>   emulates an 80-column terminal host-side, so you are not forced to pad every line to 72
>   columns.
> - A name longer than six characters is **silently truncated to six** — the common historical
>   behavior — so `LONGNAME` and `LONGNAM` denote the same variable. forterp does not warn; keep
>   names within six characters to avoid surprise collisions.
> - The standard's only comment marker is `C` in column 1; forterp also accepts `*` in column 1 as
>   a comment in every dialect. The **`!` end-of-line comment is a FORTRAN-10 extension** and is
>   *rejected* under strict `F66` — there is no inline comment character in standard FORTRAN 66.
>   See [Appendix C](C-forterp-extensions.md).
