# Appendix A — Intrinsic function reference

The functions built into FORTRAN 77 *(§15.10, Table 5)*. Most are **generic**: you call the
generic name (e.g. `ABS`) and the result type follows the argument type. The **specific** names
(e.g. `IABS`, `DABS`, `CABS`) name one type each; only a specific name may be passed as an actual
argument, and the type-conversion / `MAX` / `MIN` / lexical specifics may not be passed at all.

Throughout: `I` integer, `R` real, `D` double precision, `C` complex, `Ch` character, `L` logical.

## Type conversion

| Generic | Specifics | Result | Meaning |
|---|---|---|---|
| `INT` | `IFIX` (R→I), `IDINT` (D→I) | I | convert to integer, truncating toward zero |
| `REAL` | `FLOAT` (I→R), `SNGL` (D→R) | R | convert to real |
| `DBLE` | — | D | convert to double precision |
| `CMPLX` | — | C | convert to complex (`CMPLX(x)` → x+0i; `CMPLX(x,y)` → x+yi) |
| `ICHAR` | — | I | code of a single character |
| `CHAR` | — | Ch | character with a given code (inverse of `ICHAR`) |

## Truncation & rounding

| Generic | Specifics | Meaning |
|---|---|---|
| `AINT` | `DINT` | truncate to a whole number (toward zero), result real/double |
| `ANINT` | `DNINT` | nearest whole number (round half away from zero), result real/double |
| `NINT` | `IDNINT` | nearest **integer** |

## Arithmetic

| Generic | Specifics | Meaning |
|---|---|---|
| `ABS` | `IABS`, `DABS`, `CABS` | absolute value (`CABS` is the complex modulus, a real) |
| `MOD` | `AMOD`, `DMOD` | remainder of `a/b` (sign of the dividend) |
| `SIGN` | `ISIGN`, `DSIGN` | `\|a\|` with the sign of `b` |
| `DIM` | `IDIM`, `DDIM` | positive difference: `a−b` if `a>b`, else 0 |
| `DPROD` | — | double-precision product of two reals |
| `MAX` | `MAX0`,`AMAX1`,`DMAX1`,`AMAX0`,`MAX1` | largest of two or more arguments |
| `MIN` | `MIN0`,`AMIN1`,`DMIN1`,`AMIN0`,`MIN1` | smallest of two or more arguments |

## Character

| Generic | Meaning |
|---|---|
| `LEN` | declared length of a character entity (its argument need not be defined) |
| `INDEX(s, t)` | position of the first occurrence of `t` in `s`, else 0 |
| `LGE`, `LGT`, `LLE`, `LLT` | lexical `≥` / `>` / `≤` / `<` of two strings (logical), by the ASCII collating sequence |

## Complex

| Generic | Meaning |
|---|---|
| `AIMAG(z)` | imaginary part of `z` (a real) |
| `CONJG(z)` | complex conjugate of `z` |

## Square root, exponential, logarithm

| Generic | Specifics | Meaning |
|---|---|---|
| `SQRT` | `DSQRT`, `CSQRT` | square root |
| `EXP` | `DEXP`, `CEXP` | e raised to the argument |
| `LOG` | `ALOG`, `DLOG`, `CLOG` | natural logarithm |
| `LOG10` | `ALOG10`, `DLOG10` | base-10 logarithm |

## Trigonometric & hyperbolic (arguments in radians)

| Generic | Specifics | Meaning |
|---|---|---|
| `SIN` | `DSIN`, `CSIN` | sine |
| `COS` | `DCOS`, `CCOS` | cosine |
| `TAN` | `DTAN` | tangent |
| `ASIN` | `DASIN` | arcsine |
| `ACOS` | `DACOS` | arccosine |
| `ATAN` | `DATAN` | arctangent |
| `ATAN2` | `DATAN2` | arctangent of `y/x`, quadrant-correct |
| `SINH` | `DSINH` | hyperbolic sine |
| `COSH` | `DCOSH` | hyperbolic cosine |
| `TANH` | `DTANH` | hyperbolic tangent |

---

> **forterp notes.** All of the above are implemented with their specified semantics (`INT`
> toward zero, `NINT` round-half-away, `MOD`/`SIGN`/`DIM`, `ICHAR`/`CHAR` inverse, `INDEX` first
> occurrence, the lexical family on the ASCII collating sequence — [Appendix C](C-precedence-ascii.md)).
> An argument for which the result is not mathematically defined (e.g. `SQRT` of a negative) is
> non-fatal: it yields a value per the target model (IEEE `NaN` on `NATIVE`, a FORTRAN-10 recovery
> value on `PDP10`) — see [Chapter 6](06-expressions.md) and [Appendix D](D-forterp-extensions.md).
> forterp also exposes some DEC/FORTRAN-10 library functions beyond Table 5; those are extensions,
> not part of standard F77.
