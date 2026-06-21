#!/usr/bin/env python3
"""The simplest use of forterp as a library: run FORTRAN source from a Python string
and capture what the program prints.

`run_source(text, **kwargs)` parses + runs the source and returns the Engine. The
`printer` callback receives each record the program writes to the line printer
(unit 6); pass `emit` for terminal (TYPE) output and `readline` for input.
"""

import forterp

# The default dialect is strict ANSI FORTRAN 66, which uses Hollerith (nH) text in
# FORMATs rather than quoted strings -- so no dialect argument is needed here.
SOURCE = """\
      PROGRAM HELLO
      WRITE(6,10)
   10 FORMAT(19H HELLO FROM FORTRAN)
      END
"""


def main():
    lines = []
    forterp.run_source(SOURCE, printer=lines.append)
    print("".join(lines), end="")


if __name__ == "__main__":
    main()
