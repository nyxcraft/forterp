"""Control-flow semantics: computed/arithmetic GOTO, DO loops, IF."""

from conftest import run_int, out


def out_(eng):
    return out(eng, 1)


def test_computed_goto_selects_branch():
    body = (
        "        K=2\n        GOTO (10,20,30) K\n"
        "  10    V(1)=1\n        GOTO 99\n"
        "  20    V(1)=2\n        GOTO 99\n"
        "  30    V(1)=3\n  99    CONTINUE\n"
    )
    assert out_(run_int(body)) == 2


def test_computed_goto_out_of_range_falls_through():
    # index < 1 or > n: no jump, execution continues with the next statement
    body = (
        "        V(1)=7\n        K=0\n        GOTO (10,20,30) K\n"
        "        V(1)=5\n        GOTO 99\n"
        "  10    V(1)=1\n  20    V(1)=2\n  30    V(1)=3\n  99    CONTINUE\n"
    )
    assert out_(run_int(body)) == 5
    body4 = body.replace("        K=0\n", "        K=4\n")
    assert out_(run_int(body4)) == 5


def test_arithmetic_if_three_way():
    def arith(expr):
        body = (
            f"        N={expr}\n        IF(N) 10,20,30\n"
            "  10    V(1)=-1\n        GOTO 99\n"
            "  20    V(1)=0\n        GOTO 99\n"
            "  30    V(1)=1\n  99    CONTINUE\n"
        )
        return out_(run_int(body))

    assert arith("-5") == -1
    assert arith("0") == 0
    assert arith("5") == 1


def test_do_loop_basic_count_and_final_index():
    body = "        N=0\n        DO 100 I=1,5\n  100   N=N+1\n        V(1)=N\n        V(2)=I\n"
    eng = run_int(body)
    assert out(eng, 1) == 5
    # DEC FORTRAN-10 leaves the index at the LAST value executed (5), not 6 -- code
    # relies on this for loop-fell-through sentinels.
    assert out(eng, 2) == 5


def test_do_loop_with_step():
    body = (
        "        N=0\n        DO 100 I=1,10,2\n  100   N=N+1\n        V(1)=N\n"
        "        M=0\n        DO 200 J=10,1,-1\n  200   M=M+1\n        V(2)=M\n"
    )
    eng = run_int(body)
    assert out(eng, 1) == 5
    assert out(eng, 2) == 10


def test_do_loop_one_trip_minimum():
    # DEC FORTRAN-10 V5/V6 (F66): the body always runs at least once, so DO I=1,0
    # executes once with I=1 and leaves I=1 (last value executed), not F77 zero-trip.
    body = "        M=0\n        DO 100 I=1,0\n  100   M=M+1\n        V(1)=M\n        V(2)=I\n"
    eng = run_int(body)
    assert out(eng, 1) == 1
    assert out(eng, 2) == 1


def test_nested_do_shared_terminator():
    body = (
        "        N=0\n        DO 300 J=1,3\n        DO 300 I=1,4\n  300   N=N+1\n        V(1)=N\n"
    )
    assert out_(run_int(body)) == 12


def test_do_index_left_at_last_value_when_search_fails():
    # A GOTO-on-match search loop that finds nothing leaves the index at the LAST
    # value tested (9), which code then uses as a "nothing found" sentinel.
    # (DEC FORTRAN-10 leave-at-last, not N+1.)
    body = (
        "        M=0\n        DO 100 I=1,9\n  100   IF(I==99) GOTO 200\n"
        "        M=I\n  200   V(1)=M\n"
    )
    assert out_(run_int(body)) == 9


def test_goto_out_of_loop_abandons_remaining_iterations():
    body = (
        "        N=0\n        DO 100 I=1,10\n        N=N+1\n"
        "        IF(I==3) GOTO 200\n  100   CONTINUE\n"
        "  200   V(1)=N\n        V(2)=I\n"
    )
    eng = run_int(body)
    assert out(eng, 1) == 3
    assert out(eng, 2) == 3
