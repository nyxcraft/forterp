"""The FORMAT engine (expert API): parse a FORMAT specification, render values to text,
and read values from text under format control -- plus the bad-field error they raise.

These default to the NATIVE value model (matching `Engine`); pass `target=` for another.
"""

from forterp.fmt import parse_format, render, read_values, apply_carriage, InputConversionError

__all__ = ["parse_format", "render", "read_values", "apply_carriage", "InputConversionError"]
