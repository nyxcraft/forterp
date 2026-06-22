"""Prebuilt, reusable interpreter configurations.

forterp is configurable -- a target value model + a front-end dialect + the runtime are
all separate knobs.  Most callers just want a ready-to-run FORTRAN, so this bundles the
pieces into two named interpreters:

    forterp.fortran10 -- DEC FORTRAN-10 V5: the PDP-10 target (36-bit, packed ASCII,
                         .TRUE.=-1), the FORTRAN-10 dialect (octal/Hollerith/tab-format,
                         free-form numeric input), and the FOROTS runtime.  The faithful
                         setup for 1970s DEC programs.
    forterp.f66       -- strict ANSI FORTRAN-66: a portable NATIVE 64-bit machine, the F66
                         dialect, column-oriented input, no DEC library extensions.

Use directly::

    eng          = forterp.fortran10.run_source(open("PROG.FOR").read())
    units, errs  = forterp.fortran10.parse_dir("GAME/", exclude={"PATH"})
    eng          = forterp.fortran10.build_engine(units, emit=print)   # add builtins after

or build your own with the Interpreter class.
"""

from __future__ import annotations

import glob
import os

from forterp.dialect import F66, FORTRAN10
from forterp.engine import Engine
from forterp.parser import ParseError, parse_units
from forterp.source import DEFAULT_OPTIONS, expand_includes, scan_file, scan_text
from forterp.target import NATIVE, PDP10


class Interpreter:
    """A bundled target + dialect + runtime -- a ready-to-use FORTRAN interpreter.  Build
    engines with build_engine(); parse with parse_text()/parse_file()/parse_dir(); or do
    both with run_source()."""

    def __init__(
        self,
        target,
        dialect,
        *,
        free_form_input=None,
        dec_intrinsics=None,
        runtime=True,
        source_options=None,
    ):
        self.target = target
        self.dialect = dialect
        # Both already live on the Dialect (the single source of truth); default from it so
        # callers cannot construct a contradictory pairing. Explicit args still override.
        self.free_form_input = (
            dialect.free_form_input if free_form_input is None else free_form_input
        )
        self.dec_intrinsics = dialect.dec_intrinsics if dec_intrinsics is None else dec_intrinsics
        self.runtime = runtime
        self.source_options = source_options or DEFAULT_OPTIONS

    # ---- building engines --------------------------------------------------
    def build_engine(self, units, *, runtime=None, builtins=None, host_services=None, **kwargs):
        """An Engine pinned to this interpreter's target + dialect-derived flags.  With the
        runtime (default), installs the standard library + FOROTS binary I/O -- but never
        shadows a STDLIB library routine the program defines itself: engine builtins take
        precedence over program units, so STDLIB names that collide with a defined unit are
        skipped.  (Hardcoded intrinsics still win unless the program declares EXTERNAL --
        correct FORTRAN.)  `builtins` is an optional {name: fn} table of extra host routines,
        registered last so they extend or override the standard library.  `host_services` is an
        optional factory `fn(eng) -> facade` installed as `eng.host_services` so `@uuo` routines
        use it instead of the baseline (forterp.hostlib)."""
        kwargs.setdefault("target", self.target)
        kwargs.setdefault("free_form_input", self.free_form_input)
        kwargs.setdefault("dec_intrinsics", self.dec_intrinsics)
        eng = Engine(units, **kwargs)
        if self.runtime if runtime is None else runtime:
            import forterp  # local import: forterp.__init__ imports this module

            forterp.runtime.install_runtime(
                eng
            )  # DEC library (gated on dec_intrinsics) + FOROTS I/O
        if host_services is not None:
            eng.host_services = host_services(eng)
        if builtins:
            eng.register_builtins(dict(builtins))
        return eng

    # ---- parsing -----------------------------------------------------------
    def parse_text(self, text):
        """Parse source text -> ({name: ProgramUnit}, [(line, message), ...])."""
        stmts = expand_includes(
            scan_text(text, dialect=self.dialect, options=self.source_options).statements,
            ".",
            dialect=self.dialect,
        )
        return self._units(stmts)

    def parse_file(self, path, root=None):
        """Parse one .FOR file (INCLUDEs resolved against root or the file's directory)
        -> ({name: ProgramUnit}, [(line, message), ...])."""
        stmts = expand_includes(
            scan_file(path, dialect=self.dialect, options=self.source_options).statements,
            root or os.path.dirname(os.path.abspath(path)),
            dialect=self.dialect,
        )
        return self._units(stmts)

    def parse_dir(self, root, exclude=()):
        """Parse every ``*.FOR`` in `root` as one program.  `exclude` is a set of basenames
        to skip, matched case-insensitively with or without the .FOR suffix (e.g.
        INCLUDE-only files, or a stale prototype).  Returns ({name: ProgramUnit},
        [(file, line, message), ...])."""
        skip = {os.path.splitext(e)[0].upper() for e in exclude}
        units, errors = {}, []
        for path in sorted(glob.glob(os.path.join(root, "*.FOR"))):
            base = os.path.basename(path)
            if os.path.splitext(base)[0].upper() in skip:
                continue
            sc = scan_file(path, dialect=self.dialect, options=self.source_options)
            stmts = expand_includes(sc.statements, root, dialect=self.dialect)
            for u in parse_units(
                stmts,
                dialect=self.dialect,
                on_error=lambda s, m, b=base: errors.append((b, s.line, m)),
            ):
                units[u.name] = u
        return units, errors

    def _units(self, stmts):
        errs = []
        units = {
            u.name: u
            for u in parse_units(
                stmts, dialect=self.dialect, on_error=lambda s, m: errs.append((s.line, m))
            )
        }
        return units, errs

    # ---- parse + run -------------------------------------------------------
    def run_source(self, text, program=None, **kwargs):
        """Parse + run source text; return the Engine to inspect its state.  `program`
        selects the main PROGRAM (default: the first program unit).  Raises ParseError on
        bad source."""
        units, errors = self.parse_text(text)
        if errors:
            raise ParseError(
                "parse error(s):\n" + "\n".join(f"  line {ln}: {m}" for ln, m in errors)
            )
        eng = self.build_engine(units, **kwargs)
        return eng.run_program(program)


#: DEC FORTRAN-10 V5 -- the faithful PDP-10 setup (36-bit, FORTRAN-10 dialect, free-form).
#: Columns 73+ are dropped like real FORTRAN-10 (no shifted-column recovery by default); a
#: driver that needs reindented-deck recovery asks for it via
#: source_options=SourceOptions(recover_shifted_cols=True).
fortran10 = Interpreter(PDP10, FORTRAN10)

#: Strict ANSI FORTRAN-66 -- portable NATIVE machine, F66 dialect, column input, no DEC
#: library (free_form_input / dec_intrinsics are taken from the F66 dialect).
f66 = Interpreter(NATIVE, F66)
