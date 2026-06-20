"""The prebuilt Interpreter configurations (forterp.fortran10 / forterp.f66) and the
Interpreter class -- the easy-reuse entry point.

These pin the public contract of that surface: the parse_* methods return (units, errors);
run_source raises ParseError; each interpreter is pinned to its own target + dialect; and
build_engine installs the runtime without shadowing program-defined routines. The surface
is load-bearing -- R6's migration plan has pdp10-empire import forterp.fortran10 -- but the
rest of the suite never exercises it, so it lives here.
"""

import pytest

import forterp

OK = "      PROGRAM T\n      COMMON /OUT/ V(40)\n      V(1)=2**10\n      END\n"
BAD = "      PROGRAM T\n      V(1)=2**\n      END\n"  # truncated expression
DEC = '      PROGRAM T\n      COMMON /OUT/ V(40)\n      V(1)="77\n      END\n'  # octal: DEC-only


# ---- run_source: parse + run, the easy path --------------------------------
def test_run_source_runs_and_returns_engine():
    assert forterp.fortran10.run_source(OK).commons["OUT"][0] == 1024.0


def test_run_source_raises_parse_error_on_bad_source():
    with pytest.raises(forterp.ParseError):
        forterp.fortran10.run_source(BAD)


def test_run_source_selects_the_program_unit():
    # default main = the first PROGRAM unit, regardless of declaration order
    src = (
        "      SUBROUTINE S\n      COMMON /OUT/ V(40)\n      V(1)=7\n      END\n"
        "      PROGRAM MAIN\n      COMMON /OUT/ V(40)\n      V(1)=9\n      END\n"
    )
    assert forterp.fortran10.run_source(src).commons["OUT"][0] == 9


def test_run_source_has_the_stdlib_runtime():
    src = "      PROGRAM T\n      COMMON /OUT/ V(40)\n      V(1)=SQRT(16.0)\n      END\n"
    assert forterp.fortran10.run_source(src).commons["OUT"][0] == 4.0


# ---- parse_text / parse_file / parse_dir: uniform (units, errors) ----------
def test_parse_text_returns_units_and_empty_errors():
    units, errors = forterp.fortran10.parse_text(OK)
    assert set(units) == {"T"} and errors == []


def test_parse_text_reports_errors_without_raising():
    units, errors = forterp.fortran10.parse_text(BAD)
    assert errors and errors[0][0] == 2  # (line, message): the error is on line 2


def test_parse_file_returns_units_and_errors(tmp_path):
    p = tmp_path / "PROG.FOR"
    p.write_text(OK)
    units, errors = forterp.fortran10.parse_file(str(p))
    assert set(units) == {"T"} and errors == []


def test_parse_dir_collects_every_for_file(tmp_path):
    (tmp_path / "PROG.FOR").write_text(OK)
    (tmp_path / "SUB.FOR").write_text("      SUBROUTINE S\n      END\n")
    units, errors = forterp.fortran10.parse_dir(str(tmp_path))
    assert set(units) == {"T", "S"} and errors == []


def test_parse_dir_excludes_basenames(tmp_path):
    (tmp_path / "PROG.FOR").write_text(OK)
    (tmp_path / "SKIP.FOR").write_text("      SUBROUTINE SKIP\n      END\n")
    units, _ = forterp.fortran10.parse_dir(str(tmp_path), exclude={"SKIP"})
    assert "SKIP" not in units and "T" in units


def test_parse_dir_error_tuple_carries_the_filename(tmp_path):
    # parse_dir errors are (file, line, message) -- 3-tuple -- vs parse_text's (line,
    # message), since a directory spans files. Pin the deliberate arity difference.
    (tmp_path / "BAD.FOR").write_text(BAD)
    _, errors = forterp.fortran10.parse_dir(str(tmp_path))
    assert errors and errors[0][0] == "BAD.FOR" and len(errors[0]) == 3


# ---- each interpreter is pinned to its own target + dialect ----------------
def test_fortran10_runs_on_the_pdp10_target():
    assert forterp.fortran10.run_source(OK).tgt is forterp.PDP10


def test_f66_runs_on_the_native_target():
    assert forterp.f66.run_source(OK).tgt is forterp.NATIVE


def test_dialect_is_pinned_per_interpreter():
    # octal "77 is a FORTRAN-10 lexical extension: fortran10 accepts it, f66 rejects it.
    assert forterp.fortran10.run_source(DEC).commons["OUT"][0] == 63  # octal 77 == 63
    with pytest.raises(forterp.ParseError):
        forterp.f66.run_source(DEC)


# ---- build_engine ----------------------------------------------------------
def test_build_engine_is_pinned_to_the_target_with_runtime():
    units, _ = forterp.fortran10.parse_text(OK)
    eng = forterp.fortran10.build_engine(units)
    assert eng.tgt is forterp.PDP10 and eng.binio is not None  # FOROTS codec installed


def test_build_engine_runtime_false_skips_the_runtime():
    units, _ = forterp.fortran10.parse_text(OK)
    eng = forterp.fortran10.build_engine(units, runtime=False)
    assert eng.binio is None  # no FOROTS codec without the runtime


def test_build_engine_skips_stdlib_names_a_program_defines():
    # the runtime must not register a STDLIB builtin (e.g. DATE) that collides with a
    # program-defined unit -- else it would shadow the program's own routine. The skip is
    # selective: non-colliding STDLIB names (RAN) are still installed.
    src = (
        "      PROGRAM T\n      CALL DATE(X)\n      END\n"
        "      SUBROUTINE DATE(A)\n      A=1.0\n      END\n"
    )
    units, _ = forterp.fortran10.parse_text(src)
    eng = forterp.fortran10.build_engine(units)
    assert "DATE" not in eng.builtins  # program defines DATE -> STDLIB's is skipped
    assert "RAN" in eng.builtins  # ... but other STDLIB names are still installed


# ---- the Interpreter class: roll your own ----------------------------------
def test_custom_interpreter_combines_target_and_dialect():
    # target and dialect are orthogonal: the DEC dialect on the portable NATIVE machine
    interp = forterp.Interpreter(forterp.NATIVE, forterp.FORTRAN10, free_form_input=True)
    eng = interp.run_source(OK)
    assert eng.tgt is forterp.NATIVE and eng.commons["OUT"][0] == 1024.0
