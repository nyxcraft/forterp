"""COMPLEX data type (V5 Ch4 + Table 15-1). A FORTRAN COMPLEX value is modeled as a
Python complex; declarations, (re,im) constants, mixed-mode arithmetic, the complex
intrinsics, type conversion on assignment, DATA, and I/O are exercised here.
"""

from conftest import out, run

RHEAD = "        PROGRAM T\n        COMMON /OUT/ V(40)\n        REAL V\n"
END = "        END\n"


def cx(body, decls=""):
    return run(RHEAD + decls + body + END)


def test_complex_constant_and_add():
    eng = cx(
        "        C=(1.0,2.0)+(3.0,4.0)\n        V(1)=REAL(C)\n        V(2)=AIMAG(C)\n",
        "        COMPLEX C\n",
    )
    assert out(eng, 1) == 4.0 and out(eng, 2) == 6.0


def test_complex_multiply():
    eng = cx(
        "        C=(1.0,2.0)*(3.0,4.0)\n        V(1)=REAL(C)\n        V(2)=AIMAG(C)\n",
        "        COMPLEX C\n",
    )
    assert out(eng, 1) == -5.0 and out(eng, 2) == 10.0  # (1+2i)(3+4i) = -5+10i


def test_complex_intrinsics():
    eng = cx(
        "        C=CMPLX(3.0,4.0)\n        V(1)=CABS(C)\n"
        "        V(2)=REAL(CONJG(C))\n        V(3)=AIMAG(CONJG(C))\n",
        "        COMPLEX C\n",
    )
    assert out(eng, 1) == 5.0 and out(eng, 2) == 3.0 and out(eng, 3) == -4.0


def test_complex_csqrt():
    eng = cx(
        "        C=CSQRT((-1.0,0.0))\n        V(1)=REAL(C)\n        V(2)=AIMAG(C)\n",
        "        COMPLEX C\n",
    )
    assert abs(out(eng, 1)) < 1e-9 and abs(out(eng, 2) - 1.0) < 1e-9  # sqrt(-1) = i


def test_complex_assignment_conversion():
    eng = cx(
        "        C=5.0\n        V(1)=REAL(C)\n        V(2)=AIMAG(C)\n"
        "        R=(7.0,9.0)\n        V(3)=R\n",
        "        COMPLEX C\n        REAL R\n",
    )
    assert out(eng, 1) == 5.0 and out(eng, 2) == 0.0  # real -> complex(5,0)
    assert out(eng, 3) == 7.0  # complex -> real part


def test_complex_data_statement():
    eng = cx(
        "        V(1)=REAL(C)\n        V(2)=AIMAG(C)\n",
        "        COMPLEX C\n        DATA C/(1.5,2.5)/\n",
    )
    assert out(eng, 1) == 1.5 and out(eng, 2) == 2.5


def test_complex_list_directed_output():
    eng = cx("        C=(1.0,2.0)\n        TYPE *, C\n", "        COMPLEX C\n")
    assert "".join(eng.out) == " (1.0,2.0)\n"  # full record, not just a substring


def test_complex_formatted_output_is_two_reals():
    eng = cx(
        "        C=(1.0,2.0)\n        TYPE 100, C\n  100   FORMAT(2F5.1)\n", "        COMPLEX C\n"
    )
    assert "1.0  2.0" in "".join(eng.out)  # transferred as two reals


def test_complex_formatted_input_consumes_two_reals():
    # V5 Ch4: a COMPLEX item transfers as two reals under format control -- on INPUT,
    # one complex target consumes two consecutive real fields.
    src = (
        "        PROGRAM T\n        COMMON /OUT/ V(40)\n        REAL V\n"
        "        COMPLEX C\n        ACCEPT 10, C\n"
        "  10    FORMAT(2F6.2)\n"
        "        V(1)=REAL(C)\n        V(2)=AIMAG(C)\n        END\n"
    )
    eng = run(src, inputs=["  1.50  2.50"])
    assert out(eng, 1) == 1.5 and out(eng, 2) == 2.5


def test_complex_array_formatted_input():
    # two complex array elements -> four real fields
    src = (
        "        PROGRAM T\n        COMMON /OUT/ V(40)\n        REAL V\n"
        "        COMPLEX C(2)\n        ACCEPT 10, C\n"
        "  10    FORMAT(4F5.1)\n"
        "        V(1)=REAL(C(1))\n        V(2)=AIMAG(C(1))\n"
        "        V(3)=REAL(C(2))\n        V(4)=AIMAG(C(2))\n        END\n"
    )
    eng = run(src, inputs=["  1.0  2.0  3.0  4.0"])
    assert [out(eng, i) for i in range(1, 5)] == [1.0, 2.0, 3.0, 4.0]


def test_int_and_conversions_of_complex_use_the_real_part():
    # INT / IFIX / IDINT / DBLE / AINT / NINT of a COMPLEX operate on REAL(z) (X3.9-1978 Table 5):
    # INT((1.24,5.67)) is 1, DBLE((2.5,5.5)) is 2.5. Regression for the FCVS COMPLEX-arg tests
    # (FM829), which used to crash in int()/float() on a complex argument.
    eng = cx(
        "        C=(1.24,5.67)\n        D=(2.5,5.5)\n"
        "        V(1)=INT(C)\n        V(2)=DBLE(D)\n        V(3)=AINT(C)\n        V(4)=NINT(C)\n",
        "        COMPLEX C, D\n",
    )
    assert [out(eng, i) for i in range(1, 5)] == [1.0, 2.5, 1.0, 1.0]


# ---- §6.3.3: a complex operand may be compared ONLY with .EQ./.NE. --------------------------
def test_complex_ordering_comparison_is_rejected():
    # Complex values have no ordering, so .LT./.LE./.GT./.GE. on a complex operand is a nonsense
    # comparison with no defined result -- a hard error on every dialect (gfortran rejects it in
    # all modes too), rather than the silent .FALSE. forterp used to return.
    import pytest

    import forterp

    src = (
        "      PROGRAM T\n      COMMON /O/ L\n      LOGICAL L\n      COMPLEX X,Y\n"
        "      X=(1.,0.)\n      Y=(2.,0.)\n      L=X.LT.Y\n      END\n"
    )
    for dialect in (forterp.F77, forterp.FORTRAN10):
        with pytest.raises(RuntimeError, match="cannot be ordered"):
            forterp.run_source(src, dialect=dialect, target=forterp.NATIVE)


def test_complex_equality_comparison_still_works():
    import forterp

    src = (
        "      PROGRAM T\n      COMMON /O/ L\n      LOGICAL L\n      COMPLEX X,Y\n"
        "      X=(1.,0.)\n      Y=(2.,0.)\n      L=X.NE.Y\n      END\n"
    )
    assert forterp.run_source(src, dialect=forterp.F77, target=forterp.NATIVE).commons["O"][0]
