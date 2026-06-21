#!/usr/bin/env python3
"""Drive a FORTRAN routine as a compute kernel from Python: feed it input through a
`readline` callback, let it compute, and read the result straight out of COMMON --
no scraping of printed text. `eng.commons[name]` is the block's flat word list.
"""

import forterp

SOURCE = """\
      PROGRAM ROOTS
      COMMON /OUT/ X, ROOT
      READ(5,10) X
   10 FORMAT(F10.2)
      ROOT = SQRT(X)
      END
"""


def fortran_sqrt(x):
    """Return SQRT(x) computed by the FORTRAN program above."""
    fed = iter([f"{x:10.2f}\n"])  # one input record, in the F10.2 field the READ expects
    eng = forterp.run_source(SOURCE, dialect=forterp.FORTRAN10, readline=lambda: next(fed, ""))
    return eng.commons["OUT"][1]  # /OUT/ is (X, ROOT); ROOT is the second word


def main():
    for x in (2.0, 16.0, 100.0):
        print(f"SQRT({x:6.1f}) = {fortran_sqrt(x):.6f}")


if __name__ == "__main__":
    main()
