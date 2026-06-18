# pyf66 documentation

- **[FORTRAN66.md](FORTRAN66.md)** — a language reference for the
  FORTRAN dialect `pyf66` implements (standard FORTRAN-66 plus the DEC FORTRAN-10
  extensions), written for users of this interpreter.
- **[DESIGN.md](DESIGN.md)** — the interpreter's architecture: the pipeline (source →
  lexer → parser → engine), the machine value model, memory/control models, and the four
  seams that make it standalone. For someone modifying f66.

## Authoritative standards

`pyf66` targets two specifications. The reference above summarizes them as implemented;
the primary sources are:

- **ANSI X3.9-1966, "FORTRAN"** — the FORTRAN 66 standard (the first standardized
  FORTRAN). This is the base language. The standard is archived by the ISO/IEC JTC1/SC22/WG5 Fortran committee.
- **DECsystem-10 FORTRAN-10 Language Manual (V5)** — the DEC dialect `pyf66` actually
  reproduces (the 36-bit word model, SIXBIT/A5 packing, octal/Hollerith literals,
  `IAND`/`IOR`/shift intrinsics, FOROTS binary I/O, tab-format source). This is the
  document the interpreter was validated against.

## Conformance

The interpreter is exercised against the **FCVS** (FORTRAN Compiler Validation System)
audit corpus — see `tests/fcvs/` — which checks conformance to the FORTRAN-66 standard.
Run `pytest` to execute it.
