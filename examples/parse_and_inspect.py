#!/usr/bin/env python3
"""Parse without running. `parse_source` returns a {name: ProgramUnit} dict you can
inspect -- each unit's kind (program / subroutine / function) and name -- which is the
front-end half of the pipeline (the engine is the back end). Useful for tooling: a
compile-check, a cross-reference, a linter, feeding another back end.
"""

import forterp

SOURCE = """\
      PROGRAM MAIN
      CALL WORK(3)
      END
      SUBROUTINE WORK(N)
      INTEGER N
      RETURN
      END
      INTEGER FUNCTION SQ(K)
      SQ = K * K
      END
"""


def main():
    units = forterp.parse_source(SOURCE, dialect=forterp.FORTRAN10)
    print(f"parsed {len(units)} program unit(s):")
    for name, unit in units.items():
        print(f"   {unit.kind:11s} {name}")


if __name__ == "__main__":
    main()
