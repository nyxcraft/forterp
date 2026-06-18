"""FORMAT engine (interp/fmt.py): spec parsing, output rendering, carriage
control, and input parsing -- the path every line of game display flows through.

Direct tests pin exact behavior; a few end-to-end TYPE tests confirm the wiring
(render -> carriage control -> emit). Where the engine intentionally simplifies
(I-field overflow, E as fixed-point) we document it -- the game never hits those.
"""

from f66.fmt import parse_format, render, apply_carriage, read_values
from f66.parser import pack5
from conftest import run


def sig(spec):
    """Parse a FORMAT and return [(kind, a, b), ...] for easy comparison."""
    return [(it.kind, it.a, it.b) for it in parse_format(spec)]


# ---- spec parsing ----------------------------------------------------------
def test_parse_basic_descriptors():
    assert sig("(I5)") == [("I", 5, None)]
    assert sig("(A4)") == [("A", 4, None)]
    assert sig("(F6.2)") == [("F", 6, 2)]
    assert sig("(I)") == [("I", None, None)]  # bare I, no width


def test_parse_repeat_counts():
    assert sig("(2I3)") == [("I", 3, None), ("I", 3, None)]
    assert sig("(3A1)") == [("A", 1, None)] * 3


def test_parse_literals_and_spacing():
    assert sig("(' N=',I4)") == [("lit", " N=", None), ("I", 4, None)]
    assert sig("(I3,2X,A2)") == [("I", 3, None), ("X", 2, None), ("A", 2, None)]


def test_parse_slash_and_dollar():
    assert sig("(I2/I2)") == [("I", 2, None), ("/", None, None), ("I", 2, None)]
    assert sig("(A,$)") == [("A", None, None), ("$", None, None)]


def test_parse_group_repeat():
    assert sig("(2(I2,X))") == [("I", 2, None), ("X", 1, None), ("I", 2, None), ("X", 1, None)]


def test_parse_hollerith_and_quote_escape():
    assert sig("(5HHELLO)") == [("lit", "HELLO", None)]
    assert sig("('it''s')") == [("lit", "it's", None)]


# ---- output rendering: integers --------------------------------------------
def test_render_integer_right_justified():
    assert render(parse_format("(I4)"), [42]) == ("  42", False)
    assert render(parse_format("(I4)"), [-5]) == ("  -5", False)
    assert render(parse_format("(I4)"), [0]) == ("   0", False)


def test_render_bare_integer_uses_v5_default_width_i15():
    # V5 13.2.6: a widthless I defaults to I15 (15-wide, right-justified)
    assert render(parse_format("(I)"), [42]) == ("             42", False)


def test_render_integer_overflow_yields_asterisks():
    # FORTRAN-10 V5 (AA-0944E-TB Table 13-2): a value too wide for Iw becomes '*'s.
    assert render(parse_format("(I2)"), [12345]) == ("**", False)
    assert render(parse_format("(I4)"), [42]) == ("  42", False)  # fits -> normal


def test_render_real_overflow_yields_asterisks():
    assert render(parse_format("(F4.1)"), [12345.6]) == ("****", False)
    assert render(parse_format("(F6.2)"), [3.14159]) == ("  3.14", False)  # fits


def test_render_literal_plus_integer():
    assert render(parse_format("(' N=',I4)"), [42]) == (" N=  42", False)


# ---- output rendering: reals -----------------------------------------------
def test_render_fixed_point():
    assert render(parse_format("(F6.2)"), [3.14159]) == ("  3.14", False)
    assert render(parse_format("(F6.2)"), [-1.5]) == (" -1.50", False)


def test_render_bare_fixed_point_uses_v5_default_f15_7():
    # V5 13.2.6: a widthless F defaults to F15.7
    assert render(parse_format("(F)"), [3.14159]) == ("      3.1415900", False)


def test_render_e_format_scientific():
    # V5 p13-9: E11.3 of 12.493 -> 0.125E+02 (mantissa in [0.1,1.0))
    assert render(parse_format("(E11.3)"), [12.493]) == ("  0.125E+02", False)
    assert render(parse_format("(E11.3)"), [-12.493]) == (" -0.125E+02", False)
    assert render(parse_format("(E10.3)"), [0.0]) == (" 0.000E+00", False)
    assert render(parse_format("(E10.3)"), [5.0e6]) == (" 0.500E+07", False)


def test_render_d_format_uses_d_exponent():
    assert render(parse_format("(D11.3)"), [12.493]) == ("  0.125D+02", False)


def test_render_g_format_f_or_e_by_magnitude():
    assert render(parse_format("(G12.4)"), [12.493]) == ("   12.49    ", False)  # F range
    assert render(parse_format("(G12.4)"), [5.0e6]) == ("  0.5000E+07", False)  # E range


# ---- output rendering: characters ------------------------------------------
def test_render_char_exact_and_padded():
    assert render(parse_format("(A2)"), [pack5("HI")]) == ("HI", False)
    assert render(parse_format("(A5)"), [pack5("HI")]) == ("HI   ", False)  # left-justified
    assert render(parse_format("(A)"), [pack5("HELLO")]) == ("HELLO", False)


def test_render_char_wider_field_right_justifies():
    # Aw with w greater than the data length right-justifies (blank fill on left)
    assert render(parse_format("(A8)"), [pack5("HI")]) == ("   HI   ", False)


# ---- spacing / control -----------------------------------------------------
def test_render_spaces_slash_and_dollar():
    assert render(parse_format("(I1,3X,I1)"), [1, 2]) == ("1   2", False)
    assert render(parse_format("(I1/I1)"), [1, 2]) == ("1\n2", False)
    text, suppress = render(parse_format("(I1,$)"), [7])
    assert text == "7" and suppress is True


# ---- FORMAT reversion (V5 13.2.2/13.2.10): list outlasts the descriptors ----
def test_format_reversion_repeats_descriptors():
    # one I3 descriptor, three values -> three records (reversion restarts format)
    assert render(parse_format("(I3)"), [1, 2, 3]) == ("  1\n  2\n  3", False)


def test_format_reversion_board_style():
    # Empire's board display pattern: 11 descriptors, many values -> one row per pass
    txt, _ = render(parse_format("(4I5)"), [1, 2, 3, 4, 5, 6, 7, 8])
    assert txt == "    1    2    3    4\n    5    6    7    8"


def test_format_terminates_when_list_exhausted_no_zero_pad():
    # fewer values than descriptors -> stop at the empty descriptor (no 0 padding)
    assert render(parse_format("(I3,I3,I3)"), [1, 2]) == ("  1  2", False)


# ---- carriage control: first char of a record controls vertical motion -----
# apply_carriage emits only the PREFIX motion; the per-record line break is the
# trailing '\n' the I/O layer (do_type/do_write) appends. So a ' ' single-space
# record carries no extra newline -> consecutive records are single-spaced.
def test_carriage_control_translations():
    assert apply_carriage(" ABC") == "ABC"  # space -> single advance (trailing \n)
    assert apply_carriage("+ABC") == "\rABC"  # +    -> overprint (no advance)
    assert apply_carriage("0ABC") == "\nABC"  # 0    -> double space (one blank before)
    assert apply_carriage("1ABC") == "\fABC"  # 1    -> form feed
    assert apply_carriage("") == ""  # empty record -> blank line via trailing \n
    assert apply_carriage("XYZ") == "XYZ"  # non-control char kept, advance


# ---- input parsing (ACCEPT/READ side) --------------------------------------
def test_read_integers_whitespace_separated():
    assert read_values(parse_format("(I,I)"), "12 34") == [("I", 12), ("I", 34)]


def test_read_char_field_packs():
    assert read_values(parse_format("(A2)"), "HIthere") == [("A", pack5("HI"))]


def test_read_real():
    assert read_values(parse_format("(F)"), "3.14") == [("F", 3.14)]


def test_read_nonnumeric_integer_is_zero():
    assert read_values(parse_format("(I)"), "xyz") == [("I", 0)]


def test_read_x_skips_columns():
    assert read_values(parse_format("(2X,I)"), "  42") == [("I", 42)]


# ---- end-to-end through TYPE (render -> carriage -> emit) -------------------
def test_type_emits_with_carriage_control():
    src = "        PROGRAM T\n        TYPE 100, 42\n  100   FORMAT(' N=',I4)\n        END\n"
    # leading space -> single advance (consumed); record terminated by the trailing newline
    assert "".join(run(src).out) == "N=  42\n"


def test_type_overprint_carriage():
    src = "        PROGRAM T\n        TYPE 100\n  100   FORMAT('+DONE')\n        END\n"
    assert "".join(run(src).out) == "\rDONE\n"
