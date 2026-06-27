# Appendix A. Intrinsic & basic external function reference

This is the standard's function library: the **intrinsic functions** of Table 3 *(§8.2)* and the
**basic external functions** of Table 4 *(§8.3.3)*. FORTRAN 66 has no generic dispatch — you choose
the spelling that matches your data's type (`ABS` for real, `IABS` for integer, `DABS` for double
precision). All of these are verified present in forterp.

## Table 3 — intrinsic functions

| Function | Definition | Args | Name | Arg type | Result type |
|----------|-----------|:----:|------|----------|-------------|
| Absolute value | \|a\| | 1 | `ABS` | real | real |
| | | 1 | `IABS` | integer | integer |
| | | 1 | `DABS` | double | double |
| Truncation | sign of *a* × largest integer ≤ \|a\| | 1 | `AINT` | real | real |
| | | 1 | `INT` | real | integer |
| | | 1 | `IDINT` | double | integer |
| Remaindering | a₁ (mod a₂) | 2 | `AMOD` | real | real |
| | | 2 | `MOD` | integer | integer |
| Largest value | max(a₁, a₂, …) | ≥2 | `AMAX0` | integer | real |
| | | ≥2 | `AMAX1` | real | real |
| | | ≥2 | `MAX0` | integer | integer |
| | | ≥2 | `MAX1` | real | integer |
| | | ≥2 | `DMAX1` | double | double |
| Smallest value | min(a₁, a₂, …) | ≥2 | `AMIN0` | integer | real |
| | | ≥2 | `AMIN1` | real | real |
| | | ≥2 | `MIN0` | integer | integer |
| | | ≥2 | `MIN1` | real | integer |
| | | ≥2 | `DMIN1` | double | double |
| Float | integer → real | 1 | `FLOAT` | integer | real |
| Fix | real → integer | 1 | `IFIX` | real | integer |
| Transfer of sign | sign of a₂ × \|a₁\| | 2 | `SIGN` | real | real |
| | | 2 | `ISIGN` | integer | integer |
| | | 2 | `DSIGN` | double | double |
| Positive difference | a₁ − min(a₁, a₂) | 2 | `DIM` | real | real |
| | | 2 | `IDIM` | integer | integer |
| Most significant part of double | | 1 | `SNGL` | double | real |
| Real part of complex | | 1 | `REAL` | complex | real |
| Imaginary part of complex | | 1 | `AIMAG` | complex | real |
| Single → double | | 1 | `DBLE` | real | double |
| Two reals → complex | a₁ + a₂√−1 | 2 | `CMPLX` | real | complex |
| Conjugate of complex | | 1 | `CONJG` | complex | complex |

`AMOD`, `MOD`, `SIGN`, `ISIGN`, and `DSIGN` are **not defined** when the second argument is zero
*(§8.2)*.

## Table 4 — basic external functions

| Function | Definition | Args | Name | Arg type | Result type |
|----------|-----------|:----:|------|----------|-------------|
| Exponential | eᵃ | 1 | `EXP` | real | real |
| | | 1 | `DEXP` | double | double |
| | | 1 | `CEXP` | complex | complex |
| Natural logarithm | logₑ(a) | 1 | `ALOG` | real | real |
| | | 1 | `DLOG` | double | double |
| | | 1 | `CLOG` | complex | complex |
| Common logarithm | log₁₀(a) | 1 | `ALOG10` | real | real |
| | | 1 | `DLOG10` | double | double |
| Sine | sin(a) | 1 | `SIN` | real | real |
| | | 1 | `DSIN` | double | double |
| | | 1 | `CSIN` | complex | complex |
| Cosine | cos(a) | 1 | `COS` | real | real |
| | | 1 | `DCOS` | double | double |
| | | 1 | `CCOS` | complex | complex |
| Hyperbolic tangent | tanh(a) | 1 | `TANH` | real | real |
| Square root | a^(1/2) | 1 | `SQRT` | real | real |
| | | 1 | `DSQRT` | double | double |
| | | 1 | `CSQRT` | complex | complex |
| Arctangent | arctan(a) | 1 | `ATAN` | real | real |
| | | 1 | `DATAN` | double | double |
| | arctan(a₁/a₂) | 2 | `ATAN2` | real | real |
| | | 2 | `DATAN2` | double | double |
| Remaindering | a₁ (mod a₂) | 2 | `DMOD` | double | double |
| Modulus | \|a\| | 1 | `CABS` | complex | real |

```fortran
      COMMON /O/ R(3)
      REAL R
      R(1) = SQRT(2.0)
C     -> 1.41421
      R(2) = ATAN2(1.0, 1.0)
C     -> 0.78540  (pi/4)
      R(3) = ABS(SIGN(5.0, -1.0))
C     -> 5.0  (magnitude of 5, sign of -1, then absolute value)
```

> **forterp notes.** forterp implements the complete Table 3 and Table 4 libraries on every dialect.
> It also offers many **DEC FORTRAN-10 intrinsics** beyond the standard set (extra type variants and
> service routines); those are listed with the other extensions in
> [Appendix C](C-forterp-extensions.md). Stay within the tables above for portable code. On the
> default `NATIVE` target the results carry host (64-bit) precision; the `PDP10` target reproduces
> the DEC-10 library's precision and edge-case behavior.
