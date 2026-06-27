# The interactive processor
## Interactive command processor

Launched with **no file**, each command drops into an interactive command processor — a small,
FORTRAN-focused descendant of the TOPS-10 `.` prompt. It works on whole source files (F66
has no incremental-execution model), except for `IMMEDIATE` mode. The command set is the
same for all three commands; only the starting dialect differs, and `SET STD` flips it.

```text
f66> RUN prog.for             # compile + run a file        (alias EXECUTE)
f66> CHECK prog.for           # parse + list diagnostics, no run  (alias COMPILE)
f66> LOAD prog.for            # parse a file into the session
f10> START                    # run the loaded program; RESET drops it
f10> SET STD fortran10        # switch dialect / TARGET / PROGRAM between runs
f10> SET TARGET pdp10
f10> SHOW /OUT/               # inspect a COMMON block after a run; SHOW = settings
f10> !ls                      # run a host shell command
f10> @script.mon              # run commands from a file
f10> HELP                     # the command list
f10> EXIT                     # quit                          (alias QUIT)
```

### Debugging

The command processor carries a per-statement debugger/profiler (off by default — a plain `RUN`
pays nothing):

```text
f66> BREAK 7                  # breakpoint at line 7 (no arg = list); UNBREAK to remove
f66> STEP                     # the next RUN stops at the first statement
f66> RUN prog.for             # at a (dbg) prompt: step / next / cont, where, p <expr>
f66> TRACE on                 # echo each statement as it runs
f66> PROFILE on               # per-line execution counts; PROFILE (no arg) shows the report
f66> COVERAGE                 # which lines the last run reached
```

At the `(dbg)` prompt, typing a name inspects it (the engine's own evaluator); a bare
command word wins over a same-named variable, so use `p <expr>` / `=<expr>` to force
inspection.

### `IMMEDIATE` (a REPL)

```text
f66> IMMEDIATE                # alias REPL — interactive FORTRAN
*> I = 6 * 7                  # statements run as you type
*> TYPE *, I                  # 42
*> 2 + 3 * 4                  # a bare expression is evaluated and printed -> 14
```

A `DO` loop is collected across lines and run as a block; declarations accumulate in a
persistent session. `COMMON`/`EQUIVALENCE`/`NAMELIST` are out of scope for immediate mode —
put them in a file and `LOAD` it.

> The command processor's `!` shell escape and `@file` scripts run with your shell's privileges and
> are **not** reachable from a running FORTRAN program. Treat a command script as trusted
> input; don't wire the command processor to an untrusted source.
