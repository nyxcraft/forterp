# Appendix B — Edit-descriptor quick reference

A one-page summary of the `FORMAT` edit descriptors *(§13)*. Full explanations and examples are in
[Chapter 13](13-format.md). `w` = field width, `d` = decimals, `m` = minimum digits, `e` =
exponent width, `c` = column, `n`/`r`/`k` = counts.

## Repeatable (data) descriptors

| Descriptor | Type | Notes |
|---|---|---|
| `Iw`, `Iw.m` | integer | right-justified; `Iw.m` zero-fills to ≥ `m` digits |
| `Fw.d` | real | fixed-point, `d` decimals |
| `Ew.d`, `Ew.dEe` | real | scientific; `Ee` sets the exponent width |
| `Dw.d` | double | scientific, `D` exponent |
| `Gw.d`, `Gw.dEe` | real | general — `F`- or `E`-form chosen by magnitude |
| `Lw` | logical | `w−1` blanks then `T`/`F` |
| `A`, `Aw` | character | bare `A` uses the item's length; `Aw` uses width `w` |

Overflow (value won't fit `w`) prints all asterisks. On input, leading blanks are ignored and an
all-blank field reads as 0.

## Non-repeatable (control) descriptors

| Descriptor | Effect |
|---|---|
| `'text'` | literal text (output) |
| `nHtext` | Hollerith literal: the `n` characters after `H` (output) |
| `nX` | skip `n` positions |
| `Tc` | tab to absolute column `c` |
| `TLc`, `TRc` | tab left / right `c` columns |
| `/` | end the current record, start a new one |
| `:` | stop if the I/O list is exhausted |
| `S`, `SP`, `SS` | sign control: default / force `+` / suppress `+` |
| `kP` | scale factor (shift the decimal point by `k`) |
| `BN`, `BZ` | input: blanks in a numeric field are null / zeros |

## Grouping & reversion

- `rX` repeats a descriptor `r` times: `3I5` = `I5,I5,I5`.
- `r(...)` repeats a parenthesized group: `2(I3,F6.2)`.
- If the I/O list outlasts the format, processing **reverts** to the last open group, starting a
  new record each time.

## Carriage control (printing devices)

The first character of a printed record is consumed for vertical spacing: blank = one line, `0` =
two lines, `1` = new page, `+` = overprint. Begin output formats with a blank (`1X` or `' '`) so a
leading data digit isn't eaten. Whether a device "prints" is processor-determined — under forterp's
`F77` dialect standard output is a terminal (no carriage control); see
[Chapter 13](13-format.md) and [Appendix D](D-forterp-extensions.md).
