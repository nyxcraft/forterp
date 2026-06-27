# Appendix C — Operator precedence & the collating sequence

## Operator precedence

From highest (binds tightest) to lowest *(§6)*. Within a level, evaluation is left-to-right, except
`**`, which is **right-to-left**.

| Rank | Operators | Notes |
|---|---|---|
| 1 (highest) | `**` | exponentiation; right-associative (`2**3**2` = `2**(3**2)`) |
| 2 | `*` `/` | multiply, divide |
| 3 | unary `+` `-`, binary `+` `-` | (so `-A**2` = `-(A**2)`) |
| 4 | `//` | character concatenation |
| 5 | `.LT. .LE. .EQ. .NE. .GT. .GE.` | relational (yield logical) |
| 6 | `.NOT.` | logical negation |
| 7 | `.AND.` | logical and |
| 8 | `.OR.` | logical or |
| 9 (lowest) | `.EQV.` `.NEQV.` | logical equivalence / non-equivalence |

Across families this is the ladder **arithmetic > character > relational > logical**, so
`2 + 3 .GT. 4` is `(2+3) .GT. 4` and needs no parentheses. You may not place two operators
adjacently — write `A**(-B)`, not `A**-B`. Parenthesized subexpressions are evaluated as written
and not regrouped.

## The collating sequence

Character comparison (`.LT.`, the `LGE`/`LGT`/`LLE`/`LLT` intrinsics, etc.) uses a **collating
sequence**. The standard requires only a partial order *(§3.1.5)*:

- `A < B < … < Z`,
- `0 < 1 < … < 9`,
- blank is less than both `A` and `0`,
- the letters and digits are not interleaved (all digits precede `A`, or all follow `Z`).

`.EQ.` and `.NE.` do not depend on the collating sequence. When two character operands differ in
length, the shorter is blank-padded on the right before comparison, so `'HI'` equals `'HI   '`.

---

> **forterp notes.** forterp uses the **ASCII** collating sequence, which satisfies the standard's
> partial order (in ASCII: blank 32, digits 48–57, upper-case letters 65–90 — so blank < digits <
> letters). `ICHAR`/`CHAR` therefore map to ASCII codes.
