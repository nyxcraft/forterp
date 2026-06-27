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
    ap.add_argument("-?", action="help", default=argparse.SUPPRESS, help="show this help and exit")
    ap.add_argument(
        "-V",
        "--version",
        action="count",
        default=0,
        dest="version",
        help="print the version and exit; repeat (-VV) for dialect/target/host build info",
    )
    ap.add_argument(
        "file",
        nargs="*",
        help="FORTRAN source file(s) to run (several are linked by unit name into one program); "
        "'-' reads the program from stdin; any *.py argument is imported and its @fcall/@uuo "
        "host routines registered, with its optional register(eng) hook called for engine setup "
        "(OPEN devices, COMMON priming); omit all for interactive mode",
    )
    ap.add_argument("-c", metavar="CMD", help="run the FORTRAN program passed as a string")
    ap.add_argument(
        "-i",
        action="store_true",
        help="after running, enter the interactive command processor (inspect COMMON, continue)",
    )
    ap.add_argument(
        "-q", "--quiet", action="store_true", help="suppress the interactive startup banner"
    )
    ap.add_argument("-u", action="store_true", help="force unbuffered stdout/stderr")
    ap.add_argument(
        "-x", action="store_true", help="skip the first line of the source (e.g. a #! shebang)"
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
        "--mount",
        metavar="DEV=DIR",
        action="append",
        default=[],
        help="mount logical device DEV: on host directory DIR -- OPEN(DEVICE='DEV',FILE='F') "
        "then reads/writes DIR/F (repeatable; e.g. --mount GAM=./maps)",
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
    ap.add_argument(
        "--word-memory",
        action="store_true",
        help="store COMMON/EQUIVALENCE in word-addressable memory so cross-type punning is "
        "bit-faithful (a REAL read as INTEGER yields the genuine machine word). PDP10 target "
        "only; off by default (typed cells). Costs ~2x on COMMON access; see docs",
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

    if args.version:  # -V / --version (and -VV for the build line); print and exit
        line = f"{prog} {forterp.__version__}"
        if args.version >= 2:
            import platform

            dia = {"f66": "FORTRAN-66", "fortran10": "DEC FORTRAN-10"}.get(std, std)
            host = f"{platform.python_implementation()} {platform.python_version()}"
            line += f" ({dia}, {args.target.upper()} target) [{host}] on {sys.platform}"
        print(line)
        return 0

    dialect = _DIALECTS[std]
    options = forterp.SourceOptions(recover_shifted_cols=args.recover_shifted_cols)

    if args.u:  # unbuffered output (cf. python -u)
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.reconfigure(write_through=True)
            except (AttributeError, ValueError):
                pass

    # *.py args are Python host-routine modules; everything else is FORTRAN source ("-" = stdin).
    py_files = [p for p in args.file if p.endswith(".py")]
    src_files = [p for p in args.file if not p.endswith(".py")]

    if args.c is None and not src_files:  # nothing to run -> interactive command processor
        if py_files:
            ap.error("Python builtin module(s) given but no FORTRAN source to run")
        if args.check:
            ap.error("--check requires a file")
        from forterp.command import CommandProcessor

        return CommandProcessor(
            std=std, target=args.target, program=args.program, quiet=args.quiet
        ).run()

    # Gather the source: a -c string, or the file args ("-" reads stdin).
    if args.c is not None:
        pieces, name, include_dir = [args.c], "<command>", "."
    else:
        pieces = []
        for p in src_files:
            if p == "-":
                pieces.append(sys.stdin.read())
            else:
                try:
                    pieces.append(open(p, "r", errors="replace").read())
                except OSError as e:
                    ap.error(str(e))
        name = " + ".join("<stdin>" if p == "-" else os.path.basename(p) for p in src_files)
        first = next((p for p in src_files if p != "-"), None)  # INCLUDE base dir (skip stdin)
        include_dir = (os.path.dirname(first) or ".") if first else "."
    if args.x:  # skip the first line of each piece (e.g. a #! shebang)
        pieces = [p.split("\n", 1)[1] if "\n" in p else "" for p in pieces]
    text = "\n".join(pieces)

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

    captured = {}

    mounts = []  # --mount DEV=DIR (validated up front so a bad spec is a clean arg error)
    for spec in args.mount:
        dev, sep, directory = spec.partition("=")
        if not sep or not dev:
            ap.error(f"--mount expects DEV=DIR, got {spec!r}")
        mounts.append((dev, directory))

    def _setup(eng):  # capture the engine (so -i can inspect it) and run any register() hooks
        captured["eng"] = eng
        for dev, directory in mounts:
            eng.mount_device(dev, directory)
        for h in hooks:
            h(eng)

    rc = 0
    try:
        forterp.run_source(
            text,
            program=args.program,
            dialect=dialect,
            options=options,
            include_dir=include_dir,
            target=_TARGETS[args.target],
            builtins=builtins or None,  # host routines from the *.py args (after STDLIB)
            setup=_setup,
            emit=sys.stdout.write,  # TYPE / terminal output -> stdout
            printer=sys.stdout.write,  # line-printer (units 3/6) -> stdout
            readline=sys.stdin.readline,  # READ / ACCEPT <- stdin
            tty_autowrap=not args.no_wrap,  # FORTRAN-10 free-CR-LF wrap at col 80 unless --no-wrap
            word_memory=args.word_memory,  # faithful word-addressable punning (PDP10); off default
            # echo control (ECHOON/ECHOFF) -> run_source's default_terminal_echo on a real tty
        )
    except forterp.ParseError as e:
        print(e, file=sys.stderr)
        rc = 1
    except (forterp.fmt.InputConversionError, Dec10FloatError) as e:
        # bad numeric field / unrepresentable float in binary I/O, no ERR= -> clean halt
        print(f"?{e}", file=sys.stderr)
        rc = 1
    except forterp.engine.StopExecution:
        rc = 0  # explicit STOP: normal termination (run_program also swallows it)
    except KeyboardInterrupt:  # ^C while a program runs -> clean halt, not a traceback
        print("?Interrupted", file=sys.stderr)
        rc = 130
    except (RuntimeError, ValueError, ArithmeticError, RecursionError, OSError, ImportError) as e:
        # any other runtime fault (undefined unit/label/routine, step budget, bad dimension,
        # deep recursion, a file error, or a host .py module whose basename shadows a stdlib
        # import) -> a clean ?-diagnostic, never a raw traceback
        print(f"?{e}", file=sys.stderr)
        rc = 1

    if args.i:  # inspect interactively after the run (cf. python -i): SHOW /BLOCK/, IMMEDIATE, ...
        from forterp.command import CommandProcessor

        cp = CommandProcessor(std=std, target=args.target, program=args.program, quiet=args.quiet)
        cp.last_engine = captured.get("eng")
        return cp.run()
    return rc


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
