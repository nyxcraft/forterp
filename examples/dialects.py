#!/usr/bin/env python3
"""Two dialects: F66 (strict ANSI, the default) and FORTRAN10 (the DEC superset).

The same source is rejected by F66 and accepted by FORTRAN-10. By default
`parse_source` raises `ParseError` listing every diagnostic; pass an `on_error`
callback to collect them yourself and keep the (partial) parse instead.
"""

import forterp

# IMPLICIT and apostrophe-quoted string literals are FORTRAN-10 extensions, not F66.
SOURCE = """\
      PROGRAM GREET
      IMPLICIT INTEGER (A-Z)
      WRITE(6,10)
   10 FORMAT(' HELLO FROM THE DEC SUPERSET')
      END
"""


def main():
    # Strict F66 rejects it -- collect the diagnostics rather than raising.
    diags = []
    forterp.parse_source(SOURCE, dialect=forterp.F66, on_error=lambda st, m: diags.append(m))
    print("F66 rejects this program:")
    for d in diags:
        print("   ", d)

    # The FORTRAN-10 superset runs it.
    out = []
    forterp.run_source(SOURCE, dialect=forterp.FORTRAN10, printer=out.append)
    print("FORTRAN-10 runs it:", "".join(out).strip())


if __name__ == "__main__":
    main()
