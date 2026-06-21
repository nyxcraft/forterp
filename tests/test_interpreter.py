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


def test_presets_do_not_recover_shifted_columns_by_default():
    # faithful default: the prebuilt interpreters drop cols 73+ like real FORTRAN-10, no
    # shifted-column recovery. A driver that needs reindented-deck recovery opts in via
    # source_options -- it is not baked into the DEC preset.
    from forterp.source import SourceOptions

    assert forterp.fortran10.source_options.recover_shifted_cols is False
    assert forterp.f66.source_options.recover_shifted_cols is False
    # ... but the knob is there for a driver that asks for it (e.g. the pdp10-empire migration):
    custom = forterp.Interpreter(
        forterp.PDP10,
        forterp.FORTRAN10,
        free_form_input=True,
        source_options=SourceOptions(recover_shifted_cols=True),
    )
    assert custom.source_options.recover_shifted_cols is True


# ---- API-review contracts: dialect gating, no-shadow, clean errors, namespaces ----
def test_strict_f66_does_not_install_the_dec_library():
    # the DEC library (RAN/DATE/...) is gated on dec_intrinsics, so strict f66 must not
    # provide it -- calling RAN under f66 is an error, not a silent random value.
    ran = "      PROGRAM T\n      COMMON /OUT/ R\n      R = RAN(0)\n      END\n"
    with pytest.raises(RuntimeError):
        forterp.f66.run_source(ran)
    forterp.fortran10.run_source(ran)  # the DEC superset does provide it


def test_make_engine_does_not_shadow_a_program_defined_routine():
    # a program that defines its own routine sharing a STDLIB name (DATE) gets its own,
    # not the library builtin.
    src = (
        "      PROGRAM T\n      COMMON /OUT/ V(2)\n      CALL DATE(V)\n      END\n"
        "      SUBROUTINE DATE(A)\n      DIMENSION A(2)\n      A(1)=42\n      RETURN\n      END\n"
    )
    units = forterp.parse_source(src, dialect=forterp.FORTRAN10)
    eng = forterp.make_engine(units, dialect=forterp.FORTRAN10)
    eng.run_program("T")
    assert eng.commons["OUT"][0] == 42


def test_run_source_raises_value_error_when_there_is_no_program():
    # a missing or unknown program is a descriptive ValueError, not a leaked KeyError.
    with pytest.raises(ValueError):
        forterp.run_source("      SUBROUTINE S\n      END\n")
    with pytest.raises(ValueError):
        forterp.run_source("      PROGRAM T\n      END\n", program="NOPE")


def test_interpreter_derives_flags_from_its_dialect():
    # free_form_input / dec_intrinsics default from the Dialect, so a caller cannot build a
    # contradictory pairing by omission.
    fi = forterp.Interpreter(forterp.NATIVE, forterp.F66)
    assert fi.free_form_input is False and fi.dec_intrinsics is False
    f10 = forterp.Interpreter(forterp.PDP10, forterp.FORTRAN10)
    assert f10.free_form_input is True and f10.dec_intrinsics is True


def test_expert_namespaces_exist_and_root_is_slimmed():
    # expert surfaces live behind explicit namespaces ...
    assert callable(forterp.frontend.parse_units)
    assert callable(forterp.format.render)
    assert forterp.runtime.Engine is forterp.Engine
    assert hasattr(forterp.ast, "Binary")
    # ... and the misleading generic parsers are off the root (only in forterp.frontend).
    assert not hasattr(forterp, "parse_file")
    assert not hasattr(forterp, "parse_program")
    assert callable(forterp.frontend.parse_file)
