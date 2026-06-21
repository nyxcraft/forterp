"""Argument association. An array-element actual (X(I)) bound to an array dummy is
FORTRAN sequence association: the dummy's first element IS X(I), the next is X(I+1),
and so on. Regression for the 'CellRef has no attribute loc' crash that the genuine
LINPACK.FOR and RKF45.FOR demos exposed (work-vector start passed as X(I))."""

from conftest import out, run


def test_array_element_passed_as_array_argument():
    # X = 10,20,30,40,50.  ADDONE(X(2),3) increments A(1..3), i.e. X(2),X(3),X(4),
    # in place -> X = 10,21,31,41,50.  Exercises both read and write through the view.
    src = (
        "        PROGRAM T\n"
        "        COMMON /OUT/ V(40)\n"
        "        INTEGER V, X(5), I\n"
        "        DO 1 I=1,5\n"
        "    1   X(I)=I*10\n"
        "        CALL ADDONE(X(2),3)\n"
        "        DO 2 I=1,5\n"
        "    2   V(I)=X(I)\n"
        "        END\n"
        "        SUBROUTINE ADDONE(A,N)\n"
        "        INTEGER A(N), N, I\n"
        "        DO 1 I=1,N\n"
        "    1   A(I)=A(I)+1\n"
        "        END\n"
    )
    eng = run(src)
    assert [out(eng, i) for i in range(1, 6)] == [10, 21, 31, 41, 50]
