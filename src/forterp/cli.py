"""Command-line front-ends over the forterp engine.

Three console entry points (declared in pyproject [project.scripts]):
  pyf66        run a source file as strict ANSI FORTRAN-66 (dialect F66)
  pyfortran10  run it as DEC FORTRAN-10 (dialect FORTRAN10 -- the DEC superset)
  forterp      general driver; --std selects the dialect (default f66)

Each reads a .FOR file, runs its main program, and wires the program's terminal and
line-printer output to stdout and READ/ACCEPT to stdin. The dialect-named commands are
thin presets over `forterp` itself -- like g77/gfortran over gcc.
"""

from __future__ import annotations

import argparse
import sys

import forterp

_TARGETS = {"native": forterp.NATIVE, "pdp10": forterp.PDP10, "vax": forterp.VAX}
_DIALECTS = {"f66": forterp.F66, "fortran10": forterp.FORTRAN10}


def _run(argv, dialect, prog, *, allow_std):
    ap = argparse.ArgumentParser(prog=prog, description=__doc__.strip().splitlines()[0])
    ap.add_argument("file", help="FORTRAN source file to run")
    ap.add_argument(
        "--target",
        choices=_TARGETS,
        default="native",
        help="machine value model (default: native)",
    )
    ap.add_argument(
        "--program", metavar="NAME", help="main PROGRAM unit to run (default: the first)"
    )
    if allow_std:
        ap.add_argument(
            "--std",
            choices=_DIALECTS,
            default="f66",
            help="language dialect (default: f66 = strict ANSI; fortran10 = DEC superset)",
        )
    args = ap.parse_args(argv)
    if allow_std:
        dialect = _DIALECTS[args.std]

    try:
        text = open(args.file, "r", errors="replace").read()
    except OSError as e:
        ap.error(str(e))

    try:
        forterp.run_source(
            text,
            program=args.program,
            dialect=dialect,
            target=_TARGETS[args.target],
            emit=sys.stdout.write,  # TYPE / terminal output -> stdout
            printer=sys.stdout.write,  # line-printer (units 3/6) -> stdout
            readline=sys.stdin.readline,  # READ / ACCEPT <- stdin
        )
    except forterp.ParseError as e:
        print(e, file=sys.stderr)
        return 1
    return 0


def f66_main(argv=None):
    """`pyf66`: run a source file as strict ANSI FORTRAN-66."""
    return _run(argv, forterp.F66, "pyf66", allow_std=False)


def f10_main(argv=None):
    """`pyfortran10`: run a source file as DEC FORTRAN-10 (the DEC superset)."""
    return _run(argv, forterp.FORTRAN10, "pyfortran10", allow_std=False)


def main(argv=None):
    """`forterp`: general driver; `--std f66|fortran10` selects the dialect (default f66)."""
    return _run(argv, forterp.F66, "forterp", allow_std=True)
