"""Front-end pipeline stages (expert API): source reading, lexing, and parsing into AST
program units.

The focused top-level `forterp.parse_source` is usually enough. Reach here to run the
stages individually, or for the lower-level parse entry points. Note `parse_program`
applies one historical application's file conventions and is not a general parser --
prefer `parse_units` (or top-level `parse_source`) for new code.
"""

from forterp.source import scan_file, expand_includes
from forterp.lexer import tokenize, Token, LexError
from forterp.parser import parse_units, parse_program, parse_file, parse_expression

__all__ = [
    "scan_file",
    "expand_includes",
    "tokenize",
    "Token",
    "LexError",
    "parse_units",
    "parse_program",
    "parse_file",
    "parse_expression",
]
