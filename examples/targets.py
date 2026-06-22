#!/usr/bin/env python3
"""The machine value model is pluggable. The same integer overflow yields different
results on a 64-bit host word (NATIVE, the default) versus a 36-bit PDP-10
word -- forterp models each target's arithmetic, not Python's unbounded integers.
"""

import forterp

# Compute 2**40 by repeated doubling, stored in COMMON so Python can read it back.
SOURCE = """\
      PROGRAM OVER
      COMMON /OUT/ N
      N = 1
      DO 1 I = 1, 40
    1 N = N * 2
      END
"""


def main():
    for name, target in (("native", forterp.NATIVE), ("pdp10", forterp.PDP10)):
        eng = forterp.run_source(SOURCE, target=target)
        print(f"2**40 on {name:7s} = {eng.commons['OUT'][0]}")
    print("(NATIVE's 64-bit word holds 2**40; the PDP-10's 36-bit word wraps it to 0.)")


if __name__ == "__main__":
    main()
