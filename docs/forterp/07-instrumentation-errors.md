# Instrumentation & errors
## Instrumentation: the OOB census

The engine reproduces the unchecked PDP-10 faithfully — an out-of-bounds read yields `0`, an
OOB write is dropped (the 1978 overrun behavior). `forterp.debug` lets you *observe* that
without changing it:

```python
import forterp, forterp.debug

with forterp.debug.oob_census() as census:        # mode "log" by default
    forterp.fortran10.run_source(src)
print(census.reads, census.writes)                # counts during the block
for site in census.sites:                          # per-site records (mode "log")
    print(site["op"], site["routine"], site["array"], site["idx"], site["len"])
```

The context manager restores the prior mode on exit (even on exception). For finer control
there is a standalone surface: `set_oob_mode("off"|"log"|"raise")` / `oob_mode()`,
`oob_counts()` → `(reads, writes)`, and `oob_log()` / `clear_oob_log()`. In `"raise"` mode
an overrun raises `forterp.debug.OobError` — turning the faithful overrun into a hard error
for a checker or fuzzer.

## Errors

| Exception | Raised when |
|-----------|-------------|
| `forterp.ParseError` | malformed source (front-end); message carries every diagnostic |
| `forterp.format.InputConversionError` | a bad numeric field on formatted/list-directed/NAMELIST input |
| `forterp.debug.OobError` | an out-of-bounds access while the census mode is `"raise"` |

A runtime fault inside a FORTRAN program surfaces as an ordinary Python exception
(`RuntimeError`, `ValueError`, …) out of `run_source`/`run_program`; an explicit `STOP`
raises `forterp.runtime.StopExecution`, which `run_program` swallows as normal termination.
