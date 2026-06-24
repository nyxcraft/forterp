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
import importlib.util
import os
import sys

import forterp
from forterp.forbin import Dec10FloatError

_TARGETS = forterp.target.TARGETS
_DIALECTS = forterp.dialect.DIALECTS


def _load_builtins(paths):
    """Import each ``.py`` path as a module and collect what it provides: the host routines it
    declares (``{name: fn}``, via `forterp.hostlib.builtins_in`) and any module-level
    ``register(eng)`` hook. The file's directory is put on ``sys.path`` so sibling modules can
    import each other; the module executes on import (it is host code, like any plugin loader).

    Returns ``(table, hooks)``. ``register(eng)`` lets a dropped-in module do engine setup the
    auto-discovered builtins can't express -- register an OPEN device (``eng.register_device``),
    prime COMMON, inject a monitor facade -- and is called after the engine is built.

    The directory is on ``sys.path`` and the module is in ``sys.modules`` only for the duration
    of loading (so sibling imports resolve by name); both are restored afterward, so loading a
    file named like a stdlib module (``time.py``) doesn't leave it shadowing later imports in an
    in-process caller. The loaded routines keep working -- they hold the module's namespace
    directly, independent of ``sys.modules``."""
    table, hooks = {}, []
    inserted = []  # sys.path dirs we added (remove exactly these afterward)
    saved = {}  # modname -> (was_present, prior) so sys.modules can be put back
    try:
        for path in paths:
            directory = os.path.dirname(os.path.abspath(path)) or "."
            if directory not in sys.path:
                sys.path.insert(0, directory)
                inserted.append(directory)
            modname = os.path.splitext(os.path.basename(path))[0]
            if modname not in saved:  # record the pre-existing entry once
                saved[modname] = (modname in sys.modules, sys.modules.get(modname))
            spec = importlib.util.spec_from_file_location(modname, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[modname] = module  # so dataclasses / sibling imports resolve by name
            spec.loader.exec_module(module)
            table.update(forterp.hostlib.builtins_in(module))
            hook = getattr(module, "register", None)
            if callable(hook):
                hooks.append(hook)
        return table, hooks
    finally:  # un-pollute the global import state (do not leak into an embedding process)
        for directory in inserted:
            try:
                sys.path.remove(directory)
            except ValueError:
                pass
        for modname, (was_present, prior) in saved.items():
            if was_present:
                sys.modules[modname] = prior
            else:
                sys.modules.pop(modname, None)


def _run(argv, dialect, prog, *, allow_std, default_target="native"):
    ap = argparse.ArgumentParser(prog=prog, description=__doc__.strip().splitlines()[0])
    ap.add_argument("--version", action="version", version=f"%(prog)s {forterp.__version__}")
    ap.add_argument(
        "file",
        nargs="*",
        help="FORTRAN source file(s) to run (several are linked together by unit name into one "
        "program); any *.py argument is imported and its @fcall/@uuo host routines "
        "registered, and its optional register(eng) hook called for engine setup "
        "(OPEN devices, COMMON priming); omit all for interactive mode",
    )
    ap.add_argument(
        "--target",
        choices=_TARGETS,
        default=default_target,
        help=f"machine value model (default: {default_target} for {prog})",
    )
    ap.add_argument(
        "--program", metavar="NAME", help="main PROGRAM unit to run (default: the first)"
    )
    ap.add_argument(
        "--check",
        action="store_true",
        help="parse and report all diagnostics; do not run (compile-check)",
    )
    ap.add_argument(
        "--recover-shifted-cols",
        action="store_true",
        help="recover statement text reindented past column 72 (off by default -- a faithful "
        "FORTRAN-10 compiler drops cols 73+); for a deck nudged a column or two to the right",
    )
    ap.add_argument(
        "--no-wrap",
        action="store_true",
        help="disable the FORTRAN-10 terminal free-CR-LF wrap at column 80 (TOPS-10 .TONFC); "
        "no effect under strict F66, which never wraps",
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
    options = forterp.SourceOptions(recover_shifted_cols=args.recover_shifted_cols)

    # *.py args are Python host-routine modules; everything else is FORTRAN source.
    py_files = [p for p in args.file if p.endswith(".py")]
    src_files = [p for p in args.file if not p.endswith(".py")]

    if not src_files:  # no FORTRAN to run
        if py_files:
            ap.error("Python builtin module(s) given but no FORTRAN source to run")
        if args.check:
            ap.error("--check requires a file")
        from forterp.command import CommandProcessor

        return CommandProcessor(std=std, target=args.target, program=args.program).run()

    try:  # several FORTRAN files are concatenated, then linked together by unit name
        text = "\n".join(open(p, "r", errors="replace").read() for p in src_files)
    except OSError as e:
        ap.error(str(e))
    name = " + ".join(os.path.basename(p) for p in src_files)
    # INCLUDE targets resolve against the (first) source file's directory, not the cwd.
    include_dir = os.path.dirname(src_files[0]) or "."

    if args.check:  # compile-check: list every %FTN diagnostic, don't run
        diags = []
        units = forterp.parse_source(
            text,
            dialect=dialect,
            include_dir=include_dir,
            options=options,
            on_error=lambda st, m: diags.append(m),
        )
        if diags:
            print(f"?{name}: {len(diags)} error(s)", file=sys.stderr)
            for d in diags:
                print(f"  {d}", file=sys.stderr)
            return 1
        print(f"[{name}: {len(units)} unit(s) OK]")
        return 0

    try:  # a bad builtins module is a clean ?-diagnostic, not a traceback
        builtins, hooks = _load_builtins(py_files) if py_files else ({}, [])
    except Exception as e:
        print(f"?loading {', '.join(py_files)}: {e}", file=sys.stderr)
        return 1

    try:
        forterp.run_source(
            text,
            program=args.program,
            dialect=dialect,
            options=options,
            include_dir=include_dir,
            target=_TARGETS[args.target],
            builtins=builtins or None,  # host routines from the *.py args (after STDLIB)
            setup=(lambda eng: [h(eng) for h in hooks]) if hooks else None,  # register(eng) hooks
            emit=sys.stdout.write,  # TYPE / terminal output -> stdout
            printer=sys.stdout.write,  # line-printer (units 3/6) -> stdout
            readline=sys.stdin.readline,  # READ / ACCEPT <- stdin
            tty_autowrap=not args.no_wrap,  # FORTRAN-10 free-CR-LF wrap at col 80 unless --no-wrap
            # echo control (ECHOON/ECHOFF) -> run_source's default_terminal_echo on a real tty
        )
    except forterp.ParseError as e:
        print(e, file=sys.stderr)
        return 1
    except (forterp.fmt.InputConversionError, Dec10FloatError) as e:
        # bad numeric field / unrepresentable float in binary I/O, no ERR= -> clean halt
        print(f"?{e}", file=sys.stderr)
        return 1
    except forterp.engine.StopExecution:
        return 0  # explicit STOP: normal termination (run_program also swallows it)
    except (RuntimeError, ValueError, ArithmeticError, RecursionError, OSError, ImportError) as e:
        # any other runtime fault (undefined unit/label/routine, step budget, bad dimension,
        # deep recursion, a file error, or a host .py module whose basename shadows a stdlib
        # import) -> a clean ?-diagnostic, never a raw traceback
        print(f"?{e}", file=sys.stderr)
        return 1
    return 0


def f66_main(argv=None):
    """`pyf66`: run a source file as strict ANSI FORTRAN-66."""
    return _run(argv, forterp.F66, "pyf66", allow_std=False)


def f10_main(argv=None):
    """`pyfortran10`: run a source file as DEC FORTRAN-10 (the DEC superset) on the PDP-10 machine.

    Defaults to the PDP10 target -- matching the prebuilt `forterp.fortran10` interpreter -- since
    DEC FORTRAN-10 *is* the DECsystem-10 (36-bit words, packed ASCII, .TRUE.=-1); pass
    `--target native` for the DEC language on the portable 64-bit machine instead."""
    return _run(argv, forterp.FORTRAN10, "pyfortran10", allow_std=False, default_target="pdp10")


def main(argv=None):
    """`forterp`: general driver; `--std f66|fortran10` selects the dialect (default f66)."""
    return _run(argv, forterp.F66, "forterp", allow_std=True)
