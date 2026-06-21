"""Engine construction and the installable runtime (expert/embedding API).

The `Engine` and its reference objects, plus the helpers that wire a dialect's behavior and
the DEC FORTRAN-10 library onto an engine. The focused top-level API (`run_source` /
`parse_source` / the prebuilt `f66` & `fortran10` interpreters) is usually enough; reach
here to build and drive engines yourself.
"""

from forterp.engine import Engine, Frame, StopExecution, ArrayView, TempRef
from forterp.forlib import STDLIB
from forterp import forbin, make_engine, install_runtime, engine_kwargs

__all__ = [
    "Engine",
    "Frame",
    "StopExecution",
    "ArrayView",
    "TempRef",
    "STDLIB",
    "forbin",
    "make_engine",
    "install_runtime",
    "engine_kwargs",
]
