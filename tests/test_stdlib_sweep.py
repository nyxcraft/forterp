"""Standard-library surface sweep (V5 Table 15-3 + Appendix G realtime): every
documented library routine is CALLable so source that uses it loads and runs.
Functional where cheap (sense lights/switches, RELEAS); callable no-ops where the
routine needs hardware/OS we don't have (plotting, core dumps, SORT, realtime).
"""

from conftest import run, run_int, out


def test_realtime_and_plotting_stubs_are_callable():
    eng = run_int(
        "        CALL LOCK\n        CALL RTINIT(1,2,3,4,5)\n"
        "        CALL PLOTS(-1)\n        CALL PLOT(1.0,2.0,3)\n"
        "        CALL DUMP\n        CALL UNLOCK\n        V(1)=7\n"
    )
    assert out(eng, 1) == 7  # ran to completion through the no-op stubs


def test_sense_lights():
    eng = run_int(
        "        CALL SLITE(3)\n        CALL SLITET(3,J)\n        V(1)=J\n"
        "        CALL SLITET(3,K)\n        V(2)=K\n"
    )
    assert out(eng, 1) == 1  # light 3 was on
    assert out(eng, 2) == 2  # ... and SLITET turned it off


def test_sense_switch_reads_off():
    eng = run_int("        CALL SSWTCH(5,J)\n        V(1)=J\n")
    assert out(eng, 1) == 2  # console data switches: all off -> 2


def test_releas_is_callable():
    eng = run_int("        CALL RELEAS(1)\n        V(1)=9\n")
    assert out(eng, 1) == 9


def test_tim2go_function():
    eng = run(
        "        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n        COMMON /OUT/ V(40)\n"
        "        REAL T\n        T=TIM2GO(0)\n        IF(T>100.0) V(1)=1\n        END\n"
    )
    assert out(eng, 1) == 1  # plenty of CPU time remaining


# ---- RAN / SETRAN now live in the standard library (V5 Ch15), not the driver ----
def test_ran_setran_from_stdlib_seeded_and_reproducible():
    src = (
        "        PROGRAM T\n        COMMON /OUT/ V(40)\n        REAL V\n"
        "        CALL SETRAN(777)\n        V(1)=RAN(0)\n        V(2)=RAN(0)\n"
        "        CALL SETRAN(777)\n        V(3)=RAN(0)\n        END\n"
    )
    eng = run(src)
    assert 0.0 <= out(eng, 1) < 1.0  # RAN in [0,1)
    assert out(eng, 1) != out(eng, 2)  # sequence advances
    assert out(eng, 1) == out(eng, 3)  # SETRAN(777) reproduces the sequence
