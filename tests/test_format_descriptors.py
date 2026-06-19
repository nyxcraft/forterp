"""Tier-2 FORMAT completeness (V5 Ch13): the edit descriptors and rules a
minimal program never exercises but a complete FORTRAN-10 V5 needs --
O (octal), L (logical), Tw (tab), R (alphanumeric), nP (scale factor), the
bare-descriptor default widths (13.2.6), and the Gw.d magnitude rule (Table 13-4).

The scale-factor cases reproduce the manual's worked example (E15.3 of 12.493,
p13-9) exactly, which serves as the spec oracle.
"""

from forterp.fmt import parse_format, render
from forterp.parser import pack5


def r(spec, values):
    return render(parse_format(spec), values)[0]


# ---- Ow octal (V5 13.2.8 / Table 13-2: zero-padded) ------------------------
def test_octal_zero_padded():
    assert r("(O5)", [8]) == "00010"  # 8 == 10 octal, zero-filled to 5
    assert r("(O2)", [8]) == "10"
    assert r("(O1)", [8]) == "*"  # too wide -> asterisks


def test_octal_negative_is_36bit_pattern():
    assert r("(O12)", [-1]) == "777777777777"  # -1 = all 36 bits set


def test_octal_bare_default_width_o15():
    assert r("(O)", [8]) == "000000000000010"  # bare O -> O15


# ---- Lw logical (V5 13.2.5: w-1 blanks then T/F, sign-based truth) ----------
def test_logical_output():
    assert r("(L1)", [-1]) == "T"  # .TRUE. = -1 (sign negative)
    assert r("(L1)", [0]) == "F"
    assert r("(L5)", [-1]) == "    T"
    assert r("(L5)", [0]) == "    F"


def test_logical_bare_default_width_l15():
    assert r("(L)", [-1]) == "              T"  # bare L -> L15 (14 blanks + T)


# ---- Tw tab (V5 13.2.11: position to record column; later T overwrites) -----
def test_tab_positions_field():
    assert r("('A',T5,'B')", []) == "A   B"  # 'A' at col1, 'B' at col5


def test_tab_overwrite_manual_example():
    # V5 p13-15: FORMAT(T50,'BLACK',T30,'WHITE') -> WHITE at record col 30, BLACK at 50
    out = r("(T50,'BLACK',T30,'WHITE')", [])
    assert out == " " * 29 + "WHITE" + " " * 15 + "BLACK"


# ---- Rw alphanumeric (V5 13.2.7: like A, but w<m takes RIGHTMOST w) ---------
def test_r_descriptor_rightmost_when_narrow():
    assert r("(R2)", [pack5("ABCDE")]) == "DE"  # rightmost 2 (A would give "AB")
    assert r("(R3)", [pack5("ABCDE")]) == "CDE"


def test_r_descriptor_right_justifies_when_wide():
    assert r("(R8)", [pack5("ABCDE")]) == "   ABCDE"


# ---- bare G default + G-on-integer = I conversion (13.2.3 / 13.2.6) ---------
def test_bare_g_on_integer_is_i15():
    # diagnostic 'G' fields: bare G on an integer -> I15
    assert r("(G)", [42]) == "             42"
    assert r("(3G)", [1, 2, 3]) == "              1              2              3"


# ---- Gw.d magnitude rule (V5 Table 13-4): F(w-4).x,4X or Ew.d ---------------
def test_g_fixed_form_decimals_shrink_with_magnitude():
    assert r("(G8.2)", [13.1]) == " 13.    "  # 10<=M<100 -> F4.0,4X (keeps '.')
    assert r("(G12.4)", [12.493]) == "   12.49    "
    assert r("(G12.4)", [5.0e6]) == "  0.5000E+07"  # out of F-range -> E


# ---- Fw.0 keeps the decimal point ------------------------------------------
def test_f_zero_decimals_keeps_point():
    assert r("(F5.0)", [13.0]) == "  13."


# ---- nP scale factor on E (V5 13.2.4, manual E15.3-of-12.493 table) ---------
def test_scale_factor_e_matches_manual_examples():
    assert r("(E15.3)", [12.493]) == "      0.125E+02"  # 0P
    assert r("(1PE15.3)", [12.493]) == "      1.249E+01"
    assert r("(-1PE15.3)", [12.493]) == "      0.012E+03"
    assert r("(2PE15.3)", [12.493]) == "      12.49E+00"
    assert r("(-3PE15.3)", [12.493]) == "      0.000E+05"
    assert r("(4PE15.3)", [12.493]) == "      1249.E-02"
    assert r("(6PE15.3)", [12.493]) == "    124900.E-04"


# ---- nP scale factor on F (external = internal * 10**n) ---------------------
def test_scale_factor_f_multiplies():
    assert r("(2PF8.3)", [26.451]) == "2645.100"
    assert r("(-1PF8.3)", [26.451]) == "   2.645"


def test_scale_factor_holds_until_reset():
    # one P prefix applies to subsequent E fields until a 0P resets it
    assert r("(1PE15.3,0PE15.3)", [12.493, 12.493]) == "      1.249E+01      0.125E+02"
