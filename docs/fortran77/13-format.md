# 13. `FORMAT` & edit descriptors

A **format** describes how data is laid out as text — field widths, decimal places, spacing,
literal text. It pairs with a formatted `READ`/`WRITE` ([Chapter 12](12-io.md)) and is the most
detailed part of the language *(§13)*.

## Where a format comes from

Three ways to supply one:

```fortran
      WRITE (6, 10) N, X
   10 FORMAT (I5, F8.3)               ! a labelled FORMAT statement

      WRITE (6, '(I5, F8.3)') N, X    ! a character-constant format, inline

      CHARACTER*20 FM
      FM = '(I5, F8.3)'
      WRITE (6, FM) N, X              ! a character variable holding a format
```

A format is a parenthesized list of **edit descriptors** separated by commas.

## Numeric edit descriptors (repeatable)

| Descriptor | For | Example | Output of the value |
|---|---|---|---|
| `Iw` | integer in width `w` | `I5` of `42` | `␣␣␣42` |
| `Iw.m` | integer, ≥ `m` digits (zero-filled) | `I5.3` of `42` | `␣␣042` |
| `Fw.d` | fixed-point real, `d` decimals | `F8.3` of `3.14159` | `␣␣␣3.142` |
| `Ew.d` | scientific real | `E12.4` of `1.5` | `␣␣0.1500E+01` |
| `Ew.dEe` | scientific, exponent width `e` | `E12.4E3` | `…E+001` |
| `Dw.d` | double-precision scientific (like `E`) | `D12.4` | `…D+01` |
| `Gw.d` | general — picks `F` or `E` by magnitude | `G12.4` | (F- or E-form) |

(`␣` marks a blank.) Output is right-justified in the field; if the value doesn't fit, the field
fills with asterisks (`****`). On input, leading blanks are ignored, a `+` is optional, and an
all-blank field reads as zero.

```fortran
      WRITE (6, '(I5, F8.3)') 42, 3.14159     ! ->  '   42   3.142'
      WRITE (6, '(E12.4)')    1.5             ! ->  '  0.1500E+01'
```

## Logical and character (repeatable)

| Descriptor | For | Notes |
|---|---|---|
| `Lw` | logical | outputs `w−1` blanks then `T` or `F` |
| `A` | character | uses the item's own declared length |
| `Aw` | character in width `w` | right-justify if `w` > len; leftmost `w` chars if `w` ≤ len |

```fortran
      CHARACTER*3 C
      C = 'HI'
      WRITE (6, '(A)') C            ! -> 'HI '   (the item's length, 3)
```

## Literal text and Hollerith (output)

| Descriptor | Effect |
|---|---|
| `'text'` | print the quoted text literally |
| `nHtext` | print the `n` characters after `H` (the old Hollerith form) |

```fortran
      WRITE (6, '('' answer ='', I4)') 42      ! ->  ' answer =  42'
```

## Positional & control (non-repeatable)

| Descriptor | Effect |
|---|---|
| `nX` | skip `n` positions (blanks on output) |
| `Tc` | move to absolute column `c` |
| `TLc` / `TRc` | move left / right `c` columns |
| `/` | end this record, start the next (a line break) |
| `:` | stop format processing if the I/O list is exhausted |
| `S` `SP` `SS` | sign control: default / always print `+` / suppress `+` |
| `kP` | scale factor: shift the decimal point by `k` |
| `BN` `BZ` | on input, treat blanks in a numeric field as null / as zeros |

```fortran
      WRITE (6, '(I3, /, I3)') 1, 2      ! two lines: ' 1' then ' 2'
```

## Repeat counts and groups

A descriptor may be repeated with a leading count, and a parenthesized **group** may be repeated
as a unit:

```fortran
      FORMAT (3I5)              ! same as I5, I5, I5
      FORMAT (2(I3, F6.2))      ! the group (I3,F6.2) twice
```

## Format reversion

If the I/O list has more items than the format has descriptors, the format **reverts**: a new
record starts and processing resumes at the last open parenthesis (the last group) *(§13.3)*. This
is how one `FORMAT` prints an arbitrarily long list, a record per group:

```fortran
      WRITE (6, '(5I4)') (J, J = 1, 12)   ! 5 per line, reverting -> 3 lines
```

## Carriage control (printing)

When a formatted record is sent to a device that **prints**, the **first character of each record
is not printed** — it controls vertical spacing *(§12.9.5.2.3)*:

| First char | Effect |
|---|---|
| blank | advance one line (normal) |
| `0` | advance two lines (blank line before) |
| `1` | advance to the top of a new page |
| `+` | no advance (overprint the previous line) |

This is the famous gotcha: on a printing device, `WRITE (6,'(I3)') 100` prints `00`, because the
`1` is eaten as carriage control (and starts a new page!). The cure is to begin output formats
with a blank — `1X` or `' '`:

```fortran
      WRITE (6, '('' '', I3)') 100      ! leading blank = single-space; prints ' 100'
```

Whether a given unit *prints* (interprets that first character) is left to the processor — see the
forterp notes.

## List-directed formatting

`FMT = *` skips descriptors entirely and formats each value sensibly, separated by blanks (output)
or by blanks/commas/slashes (input) — see [Chapter 12](12-io.md).

---

> **forterp notes.** The full edit-descriptor family is implemented (quick reference:
> [Appendix B](B-edit-descriptors.md)), including `Iw.m`, the scale factor, `S`/`SP`/`SS`,
> `BN`/`BZ`, the exact-exponent `Ew.dEe`, and reversion. The carriage-control question — *does the
> first character get consumed?* — is answered per dialect, because the standard leaves "which
> devices print" to the processor: under **`F77`** standard output is a **terminal** (the first
> character is ordinary data, matching gfortran), while under **`F66`/`FORTRAN10`** it is a
> **line printer** (first character consumed as carriage control). The `carriage_control` engine
> flag overrides the dialect default. See [Appendix D](D-forterp-extensions.md).
