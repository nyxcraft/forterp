"""Differential validation of forterp's formatted output against gfortran goldens.

tests/fcvs77_golden/<NAME>.out holds gfortran's stdout for each FCVS-77 routine gfortran runs
to completion (regenerate with `python tests/fcvs77_golden/regenerate.py` -- needs gfortran).
This validates forterp's formatted output -- crucially the print-and-eyeball routines that
carry no self-check -- WITHOUT gfortran at test time.

The compare normalises the ASA carriage-control column: gfortran prints column 1 literally
(`1`, ` `, `0`, `+`), while forterp interprets it (formfeed / single / double space). We drop
that column from the golden, strip forterp's interpreted formfeed, and compare the non-blank
text lines.

KNOWN_DIVERGENT is the output-conformance punch-list: routines whose output does not yet match
gfortran (early termination on an unsupported feature, or a value/format bug). The tests assert
(a) every other golden matches exactly and (b) the punch-list has no stale entries -- so fixing
a routine forces removing its name here, keeping the list honest.
"""

import glob
import os

import forterp
from forterp.engine import Engine, Frame, StopExecution
from forterp.parser import parse_units
from forterp.runtime import install_runtime
from forterp.source import expand_includes, scan_file

GOLD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fcvs77_golden")
CORPUS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fcvs77")

# Output does not yet match gfortran -- the punch-list. Shrinks as bugs are fixed.
KNOWN_DIVERGENT = {
    "FM101",
    "FM103",
    "FM108",
    "FM201",
    "FM252",
    "FM255",
    "FM256",
    "FM257",
    "FM260",
    "FM302",
    "FM311",
    "FM317",
    "FM328",
    "FM351",
    "FM352",
    "FM401",
    "FM402",
    "FM405",
    "FM406",
    "FM411",
    "FM500",
    "FM503",
    "FM509",
    "FM700",
    "FM715",
    "FM719",
    "FM722",
    "FM809",
    "FM811",
    "FM813",
    "FM815",
    "FM817",
    "FM820",
    "FM828",
    "FM829",
    "FM830",
    "FM831",
    "FM833",
    "FM834",
    # FM915 fixed -- INQUIRE ACCESS/FORM specifiers now match gfortran.
    "FM905",
    "FM907",
    "FM908",
    "FM909",
    "FM910",
    "FM912",
    "FM921",
}


def _norm(text, drop_col1):
    out = []
    for ln in text.splitlines():
        if drop_col1 and ln:
            ln = ln[1:]  # gfortran emits the ASA control column literally -- drop it
        ln = ln.replace("\f", "").rstrip()  # forterp interprets it (formfeed) -- drop that
        if ln:
            out.append(ln)
    return out


def _forterp_output(name):
    path = os.path.join(CORPUS, f"{name}.FOR")
    stmts = expand_includes(scan_file(path, dialect=forterp.F77).statements, os.path.dirname(path))
    units = parse_units(stmts, on_error=lambda s, m: None, dialect=forterp.F77)
    buf = []
    main = next((u.name for u in units if u.kind == "program"), None)
    try:
        eng = Engine(
            {u.name: u for u in units},
            emit=buf.append,
            readline=lambda: "",
            printer=buf.append,
            target=forterp.NATIVE,
            character_type=True,
        )
        install_runtime(eng)
        eng.io[5] = {"recs": [], "pos": 0, "mode": "r"}
        eng.max_steps = 50_000_000
        eng.run(Frame(eng.rts[main], {}))
    except (StopExecution, Exception):
        pass
    return "".join(buf)


def _matches(name):
    with open(os.path.join(GOLD, f"{name}.out")) as f:
        gold = _norm(f.read(), True)
    return _norm(_forterp_output(name), False) == gold


GOLDENS = sorted(os.path.basename(p)[:-4] for p in glob.glob(os.path.join(GOLD, "FM*.out")))
MATCHING = {n for n in GOLDENS if _matches(n)}


def test_goldens_present():
    # gfortran completes 131 of the 140 routines on empty input (9 need FCVS control cards).
    assert len(GOLDENS) == 131


def test_expected_outputs_match_gfortran():
    # Every routine not on the punch-list reproduces gfortran's output exactly.
    regressed = sorted(n for n in GOLDENS if n not in KNOWN_DIVERGENT and n not in MATCHING)
    assert not regressed, f"output regressed vs gfortran golden: {regressed}"


def test_punchlist_has_no_stale_entries():
    # A routine that now matches must be removed from KNOWN_DIVERGENT -- keeps it honest.
    fixed = sorted(n for n in KNOWN_DIVERGENT if n in MATCHING)
    assert not fixed, f"these now match gfortran -- drop from KNOWN_DIVERGENT: {fixed}"


def test_most_of_the_corpus_matches():
    # Floor on validated output coverage (ratchets up as the punch-list shrinks).
    assert len(MATCHING) >= 78
