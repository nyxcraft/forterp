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
