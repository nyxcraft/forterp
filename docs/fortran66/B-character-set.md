# Appendix B. The FORTRAN character set & collating sequence

## The 49-character set

A standard FORTRAN 66 program is written entirely in these **49 characters** *(§3.1)*: the 26
letters, the 10 digits, the blank, and 12 special characters.

```text
   letters   A B C D E F G H I J K L M N O P Q R S T U V W X Y Z
   digits    0 1 2 3 4 5 6 7 8 9
   blank     (space)
   special   =  +  -  *  /  (  )  ,  .  $
```

| Character | Name | Typical use |
|-----------|------|-------------|
| (blank) | blank | spacing; significant only inside Hollerith and in column rules |
| `=` | equals | assignment |
| `+` | plus | addition, unary plus |
| `-` | minus | subtraction, unary minus |
| `*` | asterisk | multiplication; `**` exponentiation; `*` in column 1 = comment (forterp) |
| `/` | slash | division; record separator in `FORMAT`; common-block delimiters |
| `(` `)` | parentheses | grouping, subscripts, argument lists |
| `,` | comma | list separator |
| `.` | decimal point | in real constants; in `.EQ.`, `.AND.`, `.TRUE.`, etc. |
| `$` | currency symbol | reserved by the standard; no standard meaning |

Any other character (lower-case letters, `:`, `;`, `'`, `!`, `#`, …) is **not** part of the standard
FORTRAN character set. Such characters may appear only inside **Hollerith** data, where any
processor-representable character — blank included — is allowed *(§3.1.4.1, §4.2.6)*.

## The collating sequence

FORTRAN 66 deliberately **does not impose a collating sequence** *(§3.1, §3.6)*. The order in which
the standard lists the characters carries no meaning, and the language provides no way to compare
character (Hollerith) data with relational operators — relational expressions compare *numbers*
only ([Chapter 6](06-expressions.md)). A program that needs to order characters must do so by its
own arithmetic on the packed Hollerith values, and the result depends on the processor's internal
representation.

> **forterp notes.**
>
> - forterp's host character representation is **ASCII**. On the default `NATIVE` target, Hollerith
>   characters are packed into 64-bit words; on the faithful `PDP10` target they are packed five
>   **7-bit ASCII** characters to a 36-bit word, exactly as DEC FORTRAN-10 did. Any program that
>   compares or unpacks Hollerith data will therefore see *different* numeric values on the two
>   targets — this is the value-model divergence discussed in
>   [Appendix C](C-forterp-extensions.md).
> - Because forterp reads ASCII source, lower-case letters and characters like `!` and `'` are
>   recognized where a dialect allows them (e.g. `!` comments and `'…'` strings under `FORTRAN10`/
>   `F77`), even though they are outside the X3.9-1966 set. Under strict `F66` they are rejected
>   outside Hollerith, as the standard requires.
> - A full ASCII table with the operator-precedence summary is in the FORTRAN 77 manual's
>   [Appendix C](../fortran77/C-precedence-ascii.md); the precedence rules there
>   (arithmetic > relational > logical, with `**` right-associative) apply unchanged to FORTRAN 66.
