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
import os
import sys

import forterp
from forterp.forbin import Dec10FloatError

_TARGETS = forterp.TARGETS
_DIALECTS = forterp.DIALECTS


def _run(argv, dialect, prog, *, allow_std):
    ap = argparse.ArgumentParser(prog=prog, description=__doc__.strip().splitlines()[0])
    ap.add_argument(
        "file",
        nargs="*",
        help="FORTRAN source file(s) to run; several are linked together by unit name, "
        "like `f77 main.f lib.f` (omit for interactive mode)",
    )
    ap.add_argument(
        "--target",
        choices=_TARGETS,
        default="native",
        help="machine value model (default: native)",
    )
    ap.add_argument(
        "--program", metavar="NAME", help="main PROGRAM unit to run (default: the first)"
    )
    ap.add_argument(
        "--check",
        action="store_true",
        help="parse and report all diagnostics; do not run (compile-check)",
    )
    if allow_std:
        ap.add_argument(
            "--std",
            choices=_DIALECTS,
            default="f66",
            help="language dialect (default: f66 = strict ANSI; fortran10 = DEC superset)",
        )
    args = ap.parse_args(argv)
    std = args.std if allow_std else ("fortran10" if dialect is forterp.FORTRAN10 else "f66")
    dialect = _DIALECTS[std]

    if not args.file:  # no file -> interactive command monitor
        if args.check:
            ap.error("--check requires a file")
        from forterp.monitor import Monitor

        return Monitor(std=std, target=args.target, program=args.program).run()

    try:  # several files are concatenated, then linked by unit name (like `f77 a.f b.f`)
        text = "\n".join(open(p, "r", errors="replace").read() for p in args.file)
    except OSError as e:
        ap.error(str(e))
    name = " + ".join(os.path.basename(p) for p in args.file)

    if args.check:  # compile-check: list every %FTN diagnostic, don't run
        diags = []
        units = forterp.parse_source(text, dialect=dialect, on_error=lambda st, m: diags.append(m))
        if diags:
            print(f"?{name}: {len(diags)} error(s)", file=sys.stderr)
            for d in diags:
                print(f"  {d}", file=sys.stderr)
            return 1
        print(f"[{name}: {len(units)} unit(s) OK]")
        return 0

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
    except (forterp.InputConversionError, Dec10FloatError) as e:
        # bad numeric field / unrepresentable float in binary I/O, no ERR= -> clean halt
        print(f"?{e}", file=sys.stderr)
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
