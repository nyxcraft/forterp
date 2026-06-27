# 1. Purpose & scope

The FORTRAN 66 standard — USA Standard X3.9-1966 — sets out **the form of a FORTRAN program and
how it is to be interpreted** *(§1.1)*. Its goal is *interchangeability*: a program written to the
standard should mean the same thing on any conforming processor. (A *processor* is the
implementation — a compiler, or in our case an interpreter.)

## What "conforming" means

A processor conforms to the standard provided it **accepts and interprets at least the forms and
relationships the standard describes** *(§1.1)*. The wording is deliberately one-sided: the
standard fixes a *floor*, not a ceiling. A processor is free to accept additional forms the
standard does not mention, as long as it does not change the meaning of a program that *is*
written to the standard.

That single sentence is what makes the **DEC FORTRAN-10 extensions** legitimate. Apostrophe-
delimited character constants, the `ENCODE`/`DECODE` statements, extra intrinsics, longer source
lines — none of these are in X3.9-1966, but offering them does not stop forterp from correctly
running a program that stays within the standard. They are additions, not contradictions.

## What the standard does *not* fix

The standard is careful to leave several things to the processor *(§1.2.1)*. It does **not**
prescribe:

- the **mechanism** by which a program is turned into something runnable;
- how a program or its data is **transcribed** to or from a medium (cards, tape, a terminal);
- the **manual operations** needed to set up and run a program;
- what happens when the **rules of interpretation fail** — i.e. the behavior of a program that is
  *not* standard-conforming;
- the behavior of a program that **exceeds the capacity** of a particular system;
- the **range or precision** of numerical quantities.

That last point matters in practice: the standard says a `REAL` datum is "a processor
approximation to the value of a real number" *(§4.2.2)* and never says *how good* an
approximation. Two conforming processors can give different last digits and both be correct.

## forterp's place

forterp is a processor for this language, written in Python. FORTRAN 66 (plus the DEC FORTRAN-10
extensions) is forterp's **default dialect** — it is what you get when you run a program without
asking for anything else:

```fortran
      PROGRAM HELLO
      WRITE(6,100)
100   FORMAT(13H HELLO, WORLD)
      STOP
      END
```

```text
$ forterp hello.for
HELLO, WORLD
```

The literal text is a **Hollerith** field, `13H` followed by exactly 13 characters — FORTRAN 66 has
no apostrophe-delimited strings (those are a FORTRAN-10 extension). The leading blank inside the
field is **carriage control** for the line printer and is consumed, not printed; both Hollerith and
carriage control are covered in [Chapter 7](07-statements.md).

> **forterp notes.** Because the standard fixes only a floor, forterp splits the things it can
> vary along two independent axes, and exposes both:
>
> - the **dialect** (the language the front end accepts) — `F66` by default, `FORTRAN10` for the
>   DEC superset, `F77` for the later standard;
> - the **target** (the value model — the "range and precision" the standard leaves open) —
>   `NATIVE` by default (the host's 64-bit integers and floats), or `PDP10` for the faithful 36-bit
>   DEC-10 representation.
>
> Selecting these is covered in the [Python API guide](../API.md) and [CLI.md](../CLI.md). The few
> places where forterp deliberately interprets a program *differently* from a strict reading of
> the standard — for faithfulness to how real FORTRAN-10 V5 behaved — are collected in
> [Appendix C](C-forterp-extensions.md); each is also flagged in a **forterp notes** box where it
> arises.
