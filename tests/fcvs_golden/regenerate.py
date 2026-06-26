"""Regenerate the FCVS golden outputs from gfortran (FORTRAN-77 / legacy mode). DEV-ONLY:
needs gfortran installed.

For every routine in tests/fcvs/ that gfortran compiles and runs to completion, capture its
stdout to <NAME>.out here. A routine whose source carries an embedded card deck (the `CARD nn`
comment images, reconstructed by fcvs_runner._card_deck) is fed that deck on stdin, exactly as
the forterp harness feeds it on unit 5 -- so the input-driven audits (list-directed READ, etc.)
run under gfortran too. These goldens let test_fcvs_golden.py validate forterp's output WITHOUT
gfortran at test time.

Routines gfortran cannot run (a compile error, or a runtime crash even with the deck) get no
golden and are listed at the end; test_fcvs_golden.py records that set (GF_CANNOT_RUN) and falls
back to forterp's own self-check for them.

Run:  python tests/fcvs_golden/regenerate.py
"""

import glob
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(HERE, "..", "fcvs")
sys.path.insert(0, os.path.join(HERE, ".."))  # for fcvs_runner._card_deck
from fcvs_runner import _card_deck  # noqa: E402


def main():
    written, skipped = [], []
    for path in sorted(glob.glob(os.path.join(CORPUS, "FM*.FOR"))):
        name = os.path.basename(path)[:-4]
        exe = os.path.join(HERE, f".{name}")
        c = subprocess.run(
            ["gfortran", "-std=legacy", "-ffixed-form", "-w", "-o", exe, path],
            capture_output=True,
        )
        if c.returncode != 0:
            skipped.append((name, "compile"))
            continue
        deck = _card_deck(path)  # the routine's own card-reader input, if any (else empty stdin)
        stdin = ("\n".join(deck) + "\n").encode() if deck else b""
        try:
            # Run in a FRESH working directory: the sequential/direct-access file audits write
            # fort.NN scratch files, and a leftover one contaminates a later run (e.g. FM411 test 2
            # FAILs if fort.8 already exists). An isolated cwd keeps each routine's run clean.
            with tempfile.TemporaryDirectory() as rundir:
                r = subprocess.run([exe], input=stdin, capture_output=True, timeout=30, cwd=rundir)
        except subprocess.TimeoutExpired:
            skipped.append((name, "timeout"))
            os.path.exists(exe) and os.remove(exe)
            continue
        os.remove(exe)
        if r.returncode != 0 or b"Fortran runtime error" in r.stderr:
            skipped.append((name, "runtime"))
            continue
        with open(os.path.join(HERE, f"{name}.out"), "w") as f:
            f.write(r.stdout.decode(errors="replace"))
        written.append(name)
    print(f"wrote {len(written)} goldens; skipped {len(skipped)}")
    print("skipped:", " ".join(f"{n}({why})" for n, why in skipped))
    return 0


if __name__ == "__main__":
    sys.exit(main())
