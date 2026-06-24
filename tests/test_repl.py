"""Immediate-mode FORTRAN (forterp.repl.Immediate): the REPL.

Tier 1 -- straight-line statements run immediately, a bare expression is evaluated
(so typing a name inspects it), and CALLs resolve against a LOADed program.
Tier 2 -- a DO loop is collected across lines and run as a block.

Driven with a scripted line source; output/diagnostics are captured."""

import forterp
from forterp.dialect import FORTRAN10
from forterp.repl import Immediate

# a loaded program the REPL can call into
LOADED = forterp.parse_source(
    "      INTEGER FUNCTION IDUB(K)\n      IDUB = K * 2\n      RETURN\n      END\n",
    dialect=FORTRAN10,
)


def drive(lines, **kw):
    it = iter(lines)
    out, err = [], []
    Immediate(write=out.append, errwrite=err.append, readline=lambda: next(it, ""), **kw).run()
    return "".join(out), "".join(err)


# ---- Tier 1: expressions, assignment, inspection ----
def test_bare_expression_is_evaluated():
    out, _ = drive(["2 + 3 * 4\n"])
    assert "14" in out


def test_assignment_then_inspect_by_name():
    out, _ = drive(["I = 7\n", "I\n"])  # I is INTEGER by the I-N rule
    assert "7\n" in out


def test_real_expression():
    out, _ = drive(["X = 2.5\n", "X * 2.0\n"])
    assert "5.0" in out


def test_logical_expression_prints_fortran_style():
    out, _ = drive(["3 .GT. 2\n"], std="fortran10")
    assert ".TRUE." in out


def test_write_runs_immediately():
    out, _ = drive(["I = 4\n", "WRITE(6,*) I\n"], std="fortran10")
    assert "4" in out


def test_call_into_a_loaded_program():
    out, _ = drive(["IDUB(21)\n"], std="fortran10", loaded=LOADED)
    assert "42" in out


# ---- Tier 1: declarations + arrays ----
def test_declaration_then_array_use():
    out, _ = drive(["INTEGER A\n", "DIMENSION A(3)\n", "A(2) = 9\n", "A(2)\n"])
    assert "9\n" in out


def test_declaration_preserves_existing_values():
    # adding a declaration rebuilds the engine; earlier values must survive
    out, _ = drive(["I = 5\n", "REAL XYZ\n", "I\n"])
    assert "5\n" in out


def test_common_is_rejected_with_guidance():
    _, err = drive(["COMMON /B/ N\n"])
    assert "LOAD" in err


# ---- Tier 2: DO block accumulation ----
def test_do_block_runs_as_a_block():
    out, _ = drive(
        [
            "ISUM = 0\n",
            "DO 10 I=1,5\n",
            "ISUM = ISUM + I\n",
            "10 CONTINUE\n",
            "ISUM\n",
        ]
    )
    assert "15\n" in out


def test_nested_do_block():
    out, _ = drive(
        [
            "N = 0\n",
            "DO 20 I=1,3\n",
            "DO 10 J=1,3\n",
            "N = N + 1\n",
            "10 CONTINUE\n",
            "20 CONTINUE\n",
            "N\n",
        ]
    )
    assert "9\n" in out


def test_blank_line_cancels_a_pending_block():
    out, err = drive(["DO 10 I=1,3\n", "\n", "2 + 2\n"])
    assert "cancelled" in err
    assert "4" in out


# ---- exit / robustness ----
def test_dot_returns_to_the_command_processor():
    # '.' ends immediate mode; the line after it is never evaluated
    out, _ = drive([".\n", "999\n"])
    assert "999" not in out


def test_runtime_error_keeps_the_session_alive():
    out, err = drive(["UNDEF(3)\n", "1 + 1\n"], std="fortran10")
    assert "2" in out  # the session survived the bad reference


# ---- the two engine/parser primitives the REPL is built on ----
def test_parse_expression_returns_ast_and_rejects_trailing():
    import pytest

    n = forterp.parser.parse_expression("2 + 3 * 4", dialect=FORTRAN10)
    assert type(n).__name__ == "Binary"  # a top-level '+' expression
    with pytest.raises(forterp.ParseError):
        forterp.parser.parse_expression("1 2", dialect=FORTRAN10)  # trailing tokens


def test_run_block_shares_store_and_resolves_loaded_calls():
    units = forterp.parse_source(
        "      INTEGER FUNCTION TWICE(K)\n      TWICE = K + K\n      END\n", dialect=FORTRAN10
    )
    sess = forterp.parse_source("      INTEGER N\n", dialect=FORTRAN10)["$MAIN"]
    sess.name = "$S"
    units["$S"] = sess
    eng = forterp.runtime.make_engine(units)
    rt = eng.rts["$S"]
    blk = forterp.parse_source("      INTEGER N\n      N = TWICE(21)\n", dialect=FORTRAN10)["$MAIN"]
    eng.run_block(rt, blk.code, blk.labels)
    assert rt.local_scalars["N"] == 42  # block mutated the shared store; call resolved
