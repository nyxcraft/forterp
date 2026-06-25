"""FORMAT engine (fmt.py): spec parsing, output rendering, carriage
control, and input parsing -- the path every formatted record flows through.

Direct tests pin exact behavior; a few end-to-end TYPE tests confirm the wiring
(render -> carriage control -> emit). Where the engine intentionally simplifies
(I-field overflow, E as fixed-point) we document it.
"""

from conftest import run
from pytest import approx

from forterp.fmt import apply_carriage, parse_format, read_values, render
from forterp.parser import pack5
from forterp.target import PDP10  # pack5 produces PDP-10 words; render them with that target


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
    assert sig("(1H.,1H,)") == [("lit", ".", None), ("lit", ",", None)]
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
    assert render(parse_format("(A2)"), [pack5("HI")], PDP10) == ("HI", False)
    assert render(parse_format("(A5)"), [pack5("HI")], PDP10) == ("HI   ", False)  # left-justified
    assert render(parse_format("(A)"), [pack5("HELLO")], PDP10) == ("HELLO", False)


def test_render_char_wider_field_right_justifies():
    # Aw with w greater than the data length right-justifies (blank fill on left)
    assert render(parse_format("(A8)"), [pack5("HI")], PDP10) == ("   HI   ", False)


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
    # board-style display: a short repeating FORMAT over many values -> one row per pass
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
def test_read_widthd_fields_by_column():
    # F66 7.2.3.6: a WIDTH'D numeric field is read by COLUMN width, so packed digits
    # split by field width ...
    assert read_values(parse_format("(I2,I3)"), "12345") == [("I", 12), ("I", 345)]
    # ... leading blanks are insignificant, embedded/trailing blanks are zeros ...
    assert read_values(parse_format("(I5)"), "  420") == [("I", 420)]
    assert read_values(parse_format("(I5)"), "4 2  ") == [("I", 40200)]
    # ... and an all-blank field is zero.
    assert read_values(parse_format("(I5)"), "     ") == [("I", 0)]
    # ... a record SHORTER than the field is blank-extended (blanks are zeros): I5 of
    # "42" reads "42___" -> 42000 (F66 7.2.3), not 42.
    assert read_values(parse_format("(I5)"), "42") == [("I", 42000)]


def test_read_widthless_descriptors_are_free_form():
    # With the FORTRAN-10 free-form input extension (free_form=True), a WIDTHLESS
    # descriptor ([DEC]; F66 requires a width) reads one free-form, space/comma/TAB-
    # delimited token -- the ADVENT-database idiom. (Under F66 it would read by column.)
    assert read_values(parse_format("(I,I)"), "12 34", free_form=True) == [("I", 12), ("I", 34)]
    assert read_values(parse_format("(4G)"), "1\t2\t44\t29", free_form=True) == [
        ("I", 1),
        ("I", 2),
        ("I", 44),
        ("I", 29),
    ]


def test_read_real_implied_decimal():
    # F66 7.2.3.6.2: an F/E/D field with no decimal point places it d digits from the
    # right; an explicit point in the field overrides d.
    assert read_values(parse_format("(F5.2)"), "12345") == [("F", approx(123.45))]
    assert read_values(parse_format("(F7.2)"), "  12.5") == [("F", approx(12.5))]


def test_read_char_field_packs():
    assert read_values(parse_format("(A2)"), "HIthere", PDP10) == [("A", pack5("HI"))]


def test_read_real():
    assert read_values(parse_format("(F)"), "3.14") == [("F", 3.14)]


def test_read_real_d_exponent():
    # Dw.d / Ew.d input: FORTRAN's D and E exponent letters are interchangeable
    assert read_values(parse_format("(D10.3)"), " 1.250D+01") == [("F", 12.5)]
    assert read_values(parse_format("(E10.3)"), " 1.250E+01") == [("F", 12.5)]
    assert read_values(parse_format("(F6.3)"), "1.5d-3") == [("F", 0.0015)]


def test_read_scale_factor():
    # F66 7.2.3.5.1: external = internal * 10**scale, so input divides by 10**scale ...
    assert read_values(parse_format("(1PF6.2)"), " 31.40") == [("F", approx(3.14))]
    assert read_values(parse_format("(-1PF6.1)"), "  3.14") == [("F", approx(31.4))]
    # ... but the scale is suspended when the field carries its own exponent
    assert read_values(parse_format("(2PE10.3)"), " 314.0E-01") == [("F", approx(31.4))]


def test_read_bz_blanks_extend_into_the_exponent():
    # F66 7.2.3.6 blanks-as-zero, taken literally, folds trailing / record-extension blanks
    # into a real field's EXPONENT -- the classic "BZ gotcha". This is INTENTIONAL conformance
    # (real FORTRAN-10 V5 does the same; numeric input was expected to be RIGHT-justified),
    # pinned here so it can't change silently. The usability escape -- a BN-style "blanks
    # ignored" option for interactive mode -- is deferred, NOT a change to this default.
    import math

    # full-width field, value left-justified: the 2 trailing blanks extend E+02 -> E+0200
    assert read_values(parse_format("(E12.4)"), "1.2500E+02  ") == [("F", 1.25e200)]
    # a record shorter than the field is blank-extended into the exponent -> overflow
    assert math.isinf(read_values(parse_format("(E10.3)"), "1.5E2")[0][1])
    # the discipline that avoids the gotcha: right-justify (no trailing blanks) -> 150.0
    assert read_values(parse_format("(E10.3)"), "   1.5E+02") == [("F", 150.0)]


def test_read_blank_null_is_the_fortran10_f77_default():
    # FORTRAN-10 V5 / F77 default is BLANK=NULL: blanks in a width'd numeric field are IGNORED,
    # not read as zeros (the ANSI F66 default). A short record padded out to the field width
    # then reads as just its significant digits -- READ(5,'(I5)') of "5" is 5, not 50000.
    assert read_values(parse_format("(I5)"), "5", blank_zero=True) == [("I", 50000)]  # F66
    assert read_values(parse_format("(I5)"), "5", blank_zero=False) == [("I", 5)]  # F10/F77
    # the field is still COLUMN-based (not free-form): I3 of "12345" -> 123 either way
    assert read_values(parse_format("(I3)"), "12345", blank_zero=False) == [("I", 123)]
    # 2G6.0 of "12 34": blanks ignored -> 1234.0, then an empty second field -> 0.0
    assert read_values(parse_format("(2G6.0)"), "12 34", blank_zero=False) == [
        ("F", 1234.0),
        ("F", 0.0),
    ]


def test_read_bn_bz_descriptors_flip_blank_mode():
    # BN / BZ flip blank interpretation mid-format (X3.9-1978 13.5.7), overriding the default.
    assert read_values(parse_format("(BZ,I5)"), "5", blank_zero=False) == [("I", 50000)]
    assert read_values(parse_format("(BN,I5)"), "5", blank_zero=True) == [("I", 5)]


def test_list_directed_input_grammar():
    # X3.9-1978 13.6: type-driven list-directed input -- INTEGER/REAL/LOGICAL/CHARACTER per the
    # io-list element, a quote-aware tokenizer ('...' keeps commas/slashes, '' -> '), null (,,),
    # repeats (r*c), the / terminator, and multi-record spanning.
    import forterp

    deck = ["25 10.75 T 'AB,/CD'", "1,,8", "2*7", "5 6 / 99", "11", "12"]

    def setup(eng):
        eng.io[5] = {"lines": list(deck), "pos": 0, "mode": "r", "text": True}

    src = (
        "      PROGRAM T\n"
        "      COMMON /O/ N(10)\n"
        "      INTEGER I, J, K\n      REAL X\n      LOGICAL L\n      CHARACTER C*8\n"
        "      I=99\n      J=88\n      K=77\n      L=.FALSE.\n"
        "      READ(5,*) I, X, L, C\n"
        "      N(1)=I\n      N(2)=NINT(X*100)\n"
        "      IF (L) N(3)=1\n      IF (C.EQ.'AB,/CD') N(4)=1\n"
        "      READ(5,*) I, J, K\n      N(5)=I\n      N(6)=J\n      N(7)=K\n"
        "      READ(5,*) I, J\n      N(8)=I+J\n"
        "      K=66\n      READ(5,*) I, J, K\n      N(9)=K\n"
        "      READ(5,*) I, J\n      N(10)=I\n"
        "      END\n"
    )
    eng = forterp.run_source(src, dialect=forterp.F77, target=forterp.NATIVE, setup=setup)
    o = eng.commons["O"]
    assert o[0] == 25 and o[1] == 1075  # INTEGER + REAL
    assert o[2] == 1 and o[3] == 1  # LOGICAL T, CHARACTER keeps the embedded comma/slash
    assert (o[4], o[5], o[6]) == (1, 88, 8)  # "1,,8" -> J untouched (null), K=8
    assert o[7] == 14  # "2*7" -> I=J=7
    assert o[8] == 66  # "5 6 / 99" -> slash stops before K, K keeps 66
    assert o[9] == 11  # "11" then "12" -> spans two records, I=11


def test_read_hollerith_field_takes_input_chars():
    # F66 7.2.3.8: an nH field reads its characters FROM the record, mutated in place
    fmt = parse_format("(5Hxxxxx)")
    read_values(fmt, "HELLO")
    assert fmt[0].kind == "lit" and fmt[0].a == "HELLO"


def test_read_nonnumeric_integer_raises():
    # V5 conformance: an illegal character in a numeric field is a runtime input error,
    # not a silent zero (an all-blank field is still zero -- that's blanks-as-zero).
    import pytest

    from forterp.fmt import InputConversionError

    with pytest.raises(InputConversionError):
        read_values(parse_format("(I)"), "xyz")
    assert read_values(parse_format("(I5)"), "     ") == [("I", 0)]  # all-blank stays 0


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


def test_carriage_control_applied_to_every_record():
    # A multi-record WRITE (FORMAT reversion or '/') carries a carriage-control character
    # in column 1 of EACH record, so it must be consumed per record -- not just the first.
    text, _ = render(parse_format("(I3)"), [1, 2, 3])  # -> "  1\n  2\n  3"
    assert apply_carriage(text) == " 1\n 2\n 3"


def test_e_descriptor_three_digit_exponent_drops_the_letter():
    # FORTRAN reserves four columns for the exponent (E+dd); a 3-digit exponent does not
    # fit, so the letter is dropped: 0.1E+101 -> 0.1+101. Two-digit exponents keep the E.
    assert render(parse_format("(E15.7)"), [1e100])[0] == "  0.1000000+101"
    assert render(parse_format("(E12.4)"), [12.493])[0] == "  0.1249E+02"
