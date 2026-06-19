"""Interactive command monitor for the forterp front-ends.

A line-oriented command loop -- a small, FORTRAN-focused descendant of the TOPS-10
monitor the ``--check`` feature came from. It operates on whole source files (RUN /
CHECK / LOAD / START), lets you SET the dialect, target, and main unit between runs,
SHOW the current settings or a COMMON block after a run, ``!`` to shell out, and ``@``
to run commands from a file. IMMEDIATE drops into interactive statement-at-a-time
FORTRAN (the REPL in forterp.repl); the monitor itself works at file granularity.

Entered when a front-end (pyf66 / pyfortran10 / forterp) is launched with no file. The
command set is identical across the three; only the starting dialect differs (pyf66 ->
f66, pyfortran10 -> fortran10), and SET STD flips it.
"""

from __future__ import annotations

import os
import subprocess
import sys

import forterp

_TARGETS = forterp.TARGETS
_DIALECTS = forterp.DIALECTS

_HELP = """\
Commands (case-insensitive):
  RUN file                    compile and run a source file   (alias EXECUTE)
  CHECK file                  parse, list diagnostics, no run  (alias COMPILE)
  LOAD file                   parse a file into the session
  START                       run the loaded program
  RESET                       drop the loaded program
  IMMEDIATE                   interactive FORTRAN (a REPL)      (alias REPL)
  BREAK [line]                set a breakpoint (no arg = list); UNBREAK to remove
  STEP                        next RUN stops at the first statement (then step/next/cont)
  TRACE [on|off]              echo each statement as it runs
  PROFILE [on|off]            collect per-line counts; no arg = show the report
  COVERAGE                    show which lines the last run reached
  SET STD f66|fortran10       switch dialect
  SET TARGET native|pdp10|vax switch the machine value model
  SET PROGRAM [name]          choose the main unit (blank = first)
  SET / SHOW                  show current settings
  SHOW /BLOCK/                show a COMMON block after a run
  !cmd                        run a host shell command
  @file                       run monitor commands from a file
  HELP                        this list
  EXIT                        quit                             (alias QUIT)
"""


class Monitor:
    """The interactive command loop. I/O is injectable for testing: `write`/`errwrite`
    take a string, `readline` returns one input line ("" at EOF)."""

    def __init__(
        self,
        std="f66",
        target="native",
        program=None,
        write=None,
        errwrite=None,
        readline=None,
    ):
        self.std = std
        self.target = target
        self.program = program
        self.units = None  # parsed-but-not-run program (from LOAD)
        self.loaded_path = None
        self.last_engine = None  # last engine that ran (for SHOW /BLOCK/)
        self.write = write or sys.stdout.write
        self.errwrite = errwrite or sys.stderr.write
        self.readline = readline or sys.stdin.readline
        self._running = False
        self._dbg = None  # lazily built Tracer (debug/profile config persists across runs)
        self._commands = {
            "RUN": self.cmd_run,
            "EXECUTE": self.cmd_run,
            "CHECK": self.cmd_check,
            "COMPILE": self.cmd_check,
            "LOAD": self.cmd_load,
            "START": self.cmd_start,
            "RESET": self.cmd_reset,
            "IMMEDIATE": self.cmd_immediate,
            "REPL": self.cmd_immediate,
            "BREAK": self.cmd_break,
            "UNBREAK": self.cmd_unbreak,
            "STEP": self.cmd_step,
            "TRACE": self.cmd_trace,
            "PROFILE": self.cmd_profile,
            "COVERAGE": self.cmd_coverage,
            "SET": self.cmd_set,
            "SHOW": self.cmd_show,
            "HELP": self.cmd_help,
            "?": self.cmd_help,
            "EXIT": self.cmd_exit,
            "QUIT": self.cmd_exit,
        }

    # ---- the loop ----
    def run(self):
        """Read-eval-print over monitor commands until EXIT or EOF. Returns 0."""
        self._running = True
        self.write(f"forterp interactive ({self.std}).  HELP for commands, EXIT to quit.\n")
        while self._running:
            self.write(self._prompt())
            line = self.readline()
            if line == "":  # EOF (Ctrl-D)
                self.write("\n")
                break
            try:
                self.dispatch(line)
            except KeyboardInterrupt:
                self.write("\n")  # ^C aborts the command, not the session
        return 0

    def dispatch(self, line):
        """Run one command line. `!`/`@` are prefixes; otherwise verb + argument."""
        line = line.strip()
        if not line:
            return
        if line.startswith("!"):
            return self.cmd_shell(line[1:].strip())
        if line.startswith("@"):
            return self.cmd_script(line[1:].strip())
        parts = line.split(None, 1)
        verb = parts[0].upper()
        arg = parts[1].strip() if len(parts) > 1 else ""
        handler = self._commands.get(verb)
        if handler is None:
            self._err(f"?Unknown command {verb}  (HELP for commands)")
            return
        handler(arg)

    # ---- commands: run / check / load / start / reset ----
    def cmd_run(self, arg):
        if not arg:
            return self._err("RUN: needs a source file")
        units = self._parse(arg)
        if units is not None:
            self._execute(units)

    def cmd_check(self, arg):
        if not arg:
            return self._err("CHECK: needs a source file")
        text = self._read(arg)
        if text is None:
            return
        diags = []
        units = forterp.parse_source(
            text, dialect=self._dialect(), on_error=lambda st, m: diags.append(m)
        )
        name = os.path.basename(arg)
        if diags:
            self._err(f"?{name}: {len(diags)} error(s)")
            for d in diags:
                self._err(f"  {d}")
        else:
            self.write(f"[{name}: {len(units)} unit(s) OK]\n")

    def cmd_load(self, arg):
        if not arg:
            return self._err("LOAD: needs a source file")
        units = self._parse(arg)
        if units is not None:
            self.units = units
            self.loaded_path = arg
            self.write(f"[loaded {os.path.basename(arg)}: {len(units)} unit(s)]\n")

    def cmd_start(self, arg):
        if not self.units:
            return self._err("START: nothing loaded (use LOAD or RUN)")
        self._execute(self.units)

    def cmd_reset(self, arg):
        self.units = None
        self.loaded_path = None
        self.last_engine = None
        self.write("[reset]\n")

    def cmd_immediate(self, arg):
        """Drop into interactive immediate-mode FORTRAN (a REPL), sharing the current
        dialect/target and any LOADed program. EXIT/'.' there returns to the monitor."""
        from forterp.repl import Immediate

        Immediate(
            std=self.std,
            target=self.target,
            loaded=self.units,
            write=self.write,
            errwrite=self.errwrite,
            readline=self.readline,
        ).run()

    # ---- commands: debug / profile (a Tracer, installed by _execute on the next RUN) ----
    def _debugger(self):
        """The session Tracer, built on first use (holds breakpoints + profile config)."""
        if self._dbg is None:
            from forterp.debug import Tracer

            self._dbg = Tracer(write=self.write, readline=self.readline, errwrite=self.errwrite)
        return self._dbg

    def cmd_break(self, arg):
        self._debugger().add_break(arg.strip())  # blank arg lists breakpoints

    def cmd_unbreak(self, arg):
        self._debugger().remove_break(arg.strip())  # blank arg clears all

    def cmd_step(self, arg):
        self._debugger().stepping = True
        self.write("[step armed -- the next RUN/START stops at the first statement]\n")

    def cmd_trace(self, arg):
        self._debugger().tracing = arg.strip().lower() != "off"
        self.write(f"[trace {'on' if self._debugger().tracing else 'off'}]\n")

    def cmd_profile(self, arg):
        a = arg.strip().lower()
        if a in ("on", "off"):
            self._debugger().profiling = a == "on"
            self.write(f"[profile {a}]\n")
        else:  # no arg -> show the last run's hot lines
            self.write(self._debugger().profile_report() + "\n")

    def cmd_coverage(self, arg):
        self.write(self._debugger().coverage_report() + "\n")

    # ---- commands: set / show ----
    def cmd_set(self, arg):
        if not arg:
            return self.cmd_show("")
        parts = arg.split(None, 1)
        key = parts[0].upper()
        val = parts[1].strip() if len(parts) > 1 else ""
        if key == "STD":
            if val.lower() not in _DIALECTS:
                return self._err("SET STD: f66 | fortran10")
            self.std = val.lower()
            self.write(f"[std = {self.std}]\n")
        elif key == "TARGET":
            if val.lower() not in _TARGETS:
                return self._err("SET TARGET: native | pdp10 | vax")
            self.target = val.lower()
            self.write(f"[target = {self.target}]\n")
        elif key == "PROGRAM":
            self.program = val or None
            self.write(f"[program = {self.program or '(first)'}]\n")
        else:
            self._err(f"SET: unknown setting {key}  (STD | TARGET | PROGRAM)")

    def cmd_show(self, arg):
        arg = arg.strip()
        if not arg:
            loaded = os.path.basename(self.loaded_path) if self.loaded_path else "(none)"
            self.write(
                f"  std     = {self.std}\n"
                f"  target  = {self.target}\n"
                f"  program = {self.program or '(first)'}\n"
                f"  loaded  = {loaded}\n"
            )
            return
        block = arg.strip("/").upper()  # accept SHOW /OUT/ or SHOW OUT
        if not self.last_engine:
            return self._err("SHOW: nothing has run yet")
        if block not in self.last_engine.commons:
            have = ", ".join(f"/{b}/" for b in self.last_engine.commons) or "(none)"
            return self._err(f"SHOW: no COMMON block /{block}/  (have: {have})")
        self.write(f"/{block}/ = {self.last_engine.commons[block]}\n")

    # ---- commands: help / exit / shell / script ----
    def cmd_help(self, arg):
        self.write(_HELP)

    def cmd_exit(self, arg):
        self._running = False

    def cmd_shell(self, arg):
        if not arg:
            return self._err("!: needs a command")
        try:
            subprocess.run(arg, shell=True)
        except OSError as e:
            self._err(str(e))

    def cmd_script(self, arg):
        if not arg:
            return self._err("@: needs a file")
        text = self._read(arg)
        if text is None:
            return
        for raw in text.splitlines():
            s = raw.strip()
            if not s or s.startswith("#"):  # '#' lines are comments
                continue
            self.dispatch(s)
            if not self._running:  # an EXIT inside the script ends the session
                break

    # ---- helpers ----
    def _prompt(self):
        return "f10> " if self.std == "fortran10" else "f66> "

    def _dialect(self):
        return _DIALECTS[self.std]

    def _err(self, msg):
        self.errwrite(msg + "\n")

    def _read(self, path):
        try:
            return open(path, errors="replace").read()
        except OSError as e:
            self._err(str(e))
            return None

    def _parse(self, path):
        text = self._read(path)
        if text is None:
            return None
        try:
            return forterp.parse_source(text, dialect=self._dialect())
        except forterp.ParseError as e:
            self._err(str(e))
            return None

    def _execute(self, units):
        dlc = self._dialect()
        eng = forterp.make_engine(
            units,
            dialect=dlc,
            target=_TARGETS[self.target],
            emit=self.write,  # TYPE / terminal output
            printer=self.write,  # line-printer (units 3/6)
            readline=self.readline,  # READ / ACCEPT
        )
        name = self.program or next((n for n, u in units.items() if u.kind == "program"), None)
        if name is None:
            return self._err("no PROGRAM unit to run (choose one with SET PROGRAM)")
        if name not in eng.rts:
            return self._err(f"no such program unit: {name}")
        self.last_engine = eng
        if self._dbg is not None and self._dbg.active:  # install debug/profile hook
            self._dbg.dialect = dlc
            self._dbg.start_run(eng, units)
            eng.tracer = self._dbg
        try:
            eng.run(forterp.Frame(eng.rts[name], {}))
        except forterp.StopExecution:
            pass
        except Exception as e:  # a program fault returns to the prompt, not a crash
            self._err(f"?runtime error: {e}")
        finally:
            if self._dbg is not None:
                self._dbg.stepping = False  # one-shot; breakpoints persist across runs
