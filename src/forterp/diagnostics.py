"""FORTRAN-10 V5 compiler diagnostics (manual Appendix F).

A faithful renderer for the subset of compiler messages this front-end can
actually detect -- the lexical and syntactic ones. The V5 message format is:

    ?FTNXXX LINE:n text      (? = fatal, % = warning, XXX = 3-letter mnemonic)

We relabel our own lexer/parser errors to the mnemonic that matches, defaulting
to NRC ("statement not recognized") for anything without a more specific match.

We deliberately do NOT emit the semantic / dataflow / optimizer diagnostics
(VND, VNI, ICD, DIM, WOP, ...): they require program analyses this interpreter
doesn't perform, and ANSI X3.9-1966 mandates no diagnostics in the first place,
so emitting none of them is standards-conformant. Diagnostics for DEC extensions
(NAMELIST, alternate RETURN, size modifiers, ...) belong with those features and
are added as each is implemented.
"""

# mnemonic -> severity character (? = fatal, % = warning)
SEVERITY = {
    "NRC": "?",  # statement not recognized          (generic fatal default)
    "FWE": "?",  # found X when expecting Y
    "CQL": "?",  # no closing quote in literal
    "IAC": "?",  # illegal ASCII character in source
    "NEX": "?",  # no exponent after D or E constant
    "NNF": "?",  # no statement number on FORMAT
    "UMP": "?",  # unmatched parentheses
    "LID": "%",  # identifier more than six characters (warning)
    "ORD": "?",  # statement out of order (F77 §3.5; strict dialects only)
    "ECC": "?",  # empty character constant (F77 §4.8.1 requires a nonempty string)
    "RNK": "?",  # array exceeds seven dimensions (F77 §5.1; lift with unlimited_rank)
    "BDU": "?",  # more than one unnamed BLOCK DATA subprogram (F77 §16.2)
}

# canonical App-F message text for the parameterless mnemonics
TEXT = {
    "NRC": "STATEMENT NOT RECOGNIZED",
    "CQL": "NO CLOSING QUOTE IN LITERAL",
    "NEX": "NO EXPONENT AFTER D OR E CONSTANT",
    "NNF": "NO STATEMENT NUMBER ON FORMAT",
    "UMP": "UNMATCHED PARENTHESES",
}


def show(tok):
    """Readable form of a token for FOUND.../EXPECTING... messages."""
    if tok is None:
        return "end of statement"
    return repr(tok.value)


def diag(mnemonic, detail=None, line=None):
    """Render '?FTNXXX LINE:n text' (LINE omitted when line is None)."""
    sev = SEVERITY.get(mnemonic, "?")
    text = detail if detail is not None else TEXT.get(mnemonic, "")
    loc = f" LINE:{line}" if line is not None else ""
    return f"{sev}FTN{mnemonic}{loc} {text}".rstrip()
