# Running & embedding
## Prebuilt interpreters and the `Interpreter` class

`forterp.fortran10` (`PDP10` + `FORTRAN10` + free-form input), `forterp.f66` (`NATIVE` +
strict `F66`), and `forterp.f77` (`NATIVE` + `F77`, with the `CHARACTER` type on) are
ready-to-run presets. Build your own with `Interpreter(target, dialect,
*, free_form_input=None, dec_intrinsics=None, runtime=True, source_options=None)` — the two
flags default from the dialect, so you can't construct a contradictory pairing.

Each interpreter offers a uniform surface:

```python
fp = forterp.fortran10

eng              = fp.run_source(src, program=None, **engine_kwargs)   # parse + run
units, errors    = fp.parse_text(src)                                  # parse a string
units, errors    = fp.parse_file("PROG.FOR")                           # parse a file
units, errors    = fp.parse_dir("src/", exclude={"SCRATCH"})           # parse a directory
eng              = fp.build_engine(units, runtime=True, **engine_kwargs)  # engine, ready to run
```

`parse_text`/`parse_file` return `(units, errors)` where `errors` is a list of
`(line, message)`; `parse_dir` errors are `(file, line, message)` (a directory spans files).
`build_engine` installs the DEC runtime (the library + FOROTS binary-I/O codec) unless
`runtime=False`, and never shadows a routine the program defines itself.

## Embedding and I/O

The `Engine` is the runtime. Build one with `forterp.runtime.make_engine(units,
dialect=None, **kwargs)` (it installs the runtime and applies the dialect's engine flags),
then `eng.run_program(name)`. The engine's host touchpoints are injected callbacks, so it
stays host-agnostic:

| `Engine`/`make_engine` kwarg | Role |
|------|------|
| `emit` | sink for terminal output (`TYPE`, list-directed, unit 5) — a `str -> None` callback |
| `printer` | sink for the line printer (units 3/6) |
| `readline` | source for `READ`/`ACCEPT` — returns one line (`""` at EOF) |
| `getch` | single-character input, if needed |
| `set_echo` | `bool -> None` — change the terminal echo mode (a program's `ECHOON`/`ECHOFF`); `run_source` defaults it to `runtime.default_terminal_echo` (flips termios `ECHO` on a tty, restored after) |
| `set_autowrap` | `bool -> None` — *optional* extra hook for the PDP-10 "free CR-LF" mode (`TRMOP.` `.TONFC`). Under the DEC dialect the engine already wraps terminal output at `tty_width` host-side, so this is only for a front-end that renders elsewhere (e.g. an ANSI terminal emitting `ESC[?7l`/`?7h`) |
| `target` | the value model (default `NATIVE`) |
| `root` | base directory for `INCLUDE` and `OPEN` file specs |
| `max_array_words` | cap on a single array/`COMMON` allocation (default 50M) |
| `dec_files` | read/write unformatted sequential files as real FOROTS binary (opt-in; default off — the portable JSON word-list otherwise) |
| `tty_width` | terminal carriage width for the FORTRAN-10 free-CR-LF wrap (default 80; `0` = no wrap) |
| `tty_autowrap` | whether terminal output wraps at `tty_width` (default on; a program toggles it via `TRMOP.` `.TONFC`) |

```python
out = []
units = forterp.parse_source(src, dialect=forterp.FORTRAN10)
eng = forterp.runtime.make_engine(units, dialect=forterp.FORTRAN10, printer=out.append)
eng.run_program()                # or run_program("MAIN")
print("".join(out))
```

Reading results back is just inspecting engine state: `eng.commons["BLK"]` (a flat word
list) is the usual channel for using FORTRAN as a compute kernel.

## Expert namespaces

The root stays focused; the rest is organized into namespaces (`import forterp` makes them
available as `forterp.<namespace>`):

| Namespace | Holds |
|-----------|-------|
| `forterp.runtime` | `Engine`, `Frame`, `make_engine`, `install_runtime`, `engine_kwargs`, `STDLIB` |
| `forterp.frontend` | the parse stages: `scan_file`, `expand_includes`, `parse_units`, `parse_expression`, `tokenize`, `Token`, `LexError` |
| `forterp.format` | the FORMAT engine: `parse_format`, `render`, `read_values`, `apply_carriage`, `InputConversionError` |
| `forterp.ast` | the AST node classes the parser produces |
| `forterp.hostlib` | declarative authoring of host builtins (below) |
| `forterp.debug` | the OOB-access census (below) and the interactive tracer/profiler |
