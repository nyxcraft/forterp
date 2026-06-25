"""Regenerate the FCVS-77 golden outputs from gfortran. DEV-ONLY: needs gfortran installed.

For every print-and-eyeball routine in tests/fcvs77/ that gfortran runs to completion (no
runtime error on empty input), capture its stdout to <NAME>.out here. These goldens let the
conformance test (test_fcvs77_golden.py) validate forterp's formatted output WITHOUT gfortran
at test time. Routines that need FCVS control-card input (gfortran aborts at EOF) are skipped
and listed at the end -- they can't be golden-compared until the input harness is modeled.

Run:  python tests/fcvs77_golden/regenerate.py
"""

import glob
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(HERE, "..", "fcvs77")


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
        try:
            r = subprocess.run([exe], input=b"", capture_output=True, timeout=30)
        except subprocess.TimeoutExpired:
            skipped.append((name, "timeout"))
            os.path.exists(exe) and os.remove(exe)
            continue
        os.remove(exe)
        if r.returncode != 0 or b"runtime error" in r.stderr:
            skipped.append((name, "needs-input"))
            continue
        with open(os.path.join(HERE, f"{name}.out"), "w") as f:
            f.write(r.stdout.decode(errors="replace"))
        written.append(name)
    print(f"wrote {len(written)} goldens; skipped {len(skipped)}")
    print("skipped:", " ".join(f"{n}({why})" for n, why in skipped))
    return 0


if __name__ == "__main__":
    sys.exit(main())
