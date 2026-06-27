"""FORTRAN intrinsic-function library and scalar value-arithmetic primitives.

INTRINSICS maps each intrinsic name to a lambda over its already-evaluated argument
list; the engine's _apply_intrinsic routes the target-dependent cases (the INT-family
wrap, LSH/ROT word width, the complex generics) using the helper tables here.
trunc_div/fort_mod are FORTRAN's integer-division and MOD semantics, shared by the
engine's arithmetic and by the MOD/AMOD/DMOD intrinsics."""

import cmath
import math

from forterp.target import PDP10


def trunc_div(a: int, b: int) -> int:
    if b == 0:
        return 0  # FORTRAN-10/FOROTS warned on divide-by-zero and CONTINUED
        #                   (non-fatal, quotient 0); never aborted like Python. The
        #                   exact recovery value is moot -- what matters is FOROTS-style
        #                   warn-and-continue, not crashing the interpreter.
    q = abs(a) // abs(b)
    return q if (a < 0) == (b < 0) else -q


def fort_mod(a, b):
    if b == 0:
        return a  # quotient 0 on divide-by-zero -> a - 0*b = a (non-fatal)
    if isinstance(a, float) or isinstance(b, float):
        return a - b * float(int(a / b))
    return a - b * trunc_div(a, b)


def _lsh(tgt, v, n):
    """Logical (unsigned) word shift; n<0 shifts right. The word width is the
    target's (PDP-10: 36-bit two's-complement); a target with no fixed width
    (mask falsy) does an unmasked Python shift."""
    u = int(v)
    if tgt.mask:
        u &= tgt.mask
    u = (u << n) if n >= 0 else (u >> -n)
    if tgt.mask:
        u &= tgt.mask
    return tgt.wrap(u)


def _rot(tgt, v, n):
    """Logical word ROTATE left by n bits (n<0 rotates right), within the target's word
    width (V5). A target with no fixed width (mask falsy) can't rotate -> returns v."""
    if not tgt.mask:
        return tgt.wrap(int(v))
    w = tgt.word_bits
    u = int(v) & tgt.mask
    n %= w  # normalize; a negative (right) rotate becomes the equivalent left rotate
    u = ((u << n) | (u >> (w - n))) & tgt.mask if n else u
    return tgt.wrap(u)


def _anint(x):  # round to nearest whole, halves away from zero
    return float(math.floor(x + 0.5)) if x >= 0 else float(math.ceil(x - 0.5))


# FORTRAN-10 V5 Appendix H, Table H-2: exact FOROTS message text for the math
# LIB domain errors, plus the recovery value each returns after the warning.
_LIB_MSG = {
    "SQRT": "Attempt to take SQRT of Negative Arg.",
    "DSQRT": "Attempt to take DSQRT of Negative Arg.",
    "ALOG": "Attempt to take LOG of Negative Arg.",
    "ALOG10": "Attempt to take LOG of Negative Arg.",
    "DLOG": "Attempt to take DLOG of Negative Arg.",
    "DLOG10": "Attempt to take DLOG of Negative Arg.",
    "ASIN": "ASIN of Arg. > 1.0 in Magnitude",
    "ACOS": "ACOS of Arg. > 1.0 in Magnitude",
}


def _rec_log(a):  # log on |x|; log of 0 -> 0.0 (avoid -inf)
    x = abs(a[0])
    return math.log(x) if x > 0 else 0.0


def _rec_log10(a):
    x = abs(a[0])
    return math.log10(x) if x > 0 else 0.0


_LIB_RECOVER = {
    "SQRT": lambda a: math.sqrt(abs(a[0])),
    "DSQRT": lambda a: math.sqrt(abs(a[0])),
    "ALOG": _rec_log,
    "ALOG10": _rec_log10,
    "DLOG": _rec_log,
    "DLOG10": _rec_log10,
    "ASIN": lambda a: math.asin(max(-1.0, min(1.0, a[0]))),
    "ACOS": lambda a: math.acos(max(-1.0, min(1.0, a[0]))),
}


_INT_RESULT = frozenset({"INT", "IFIX", "IDINT", "NINT", "IDNINT"})  # take the target's int wrap

# F77 generic dispatch: a generic transcendental called with a COMPLEX argument resolves to the
# complex (cmath) variant. The real/double cases already go through math.* (REAL is a Python
# double here); only complex needs redirecting. ABS/MAX/MIN are already polymorphic (Python
# abs/max/min), so they need no entry. (CLOG10 has no FOROTS name; LOG10 of complex is unused.)
_COMPLEX_GENERIC = {
    "SQRT": "CSQRT",
    "EXP": "CEXP",
    "LOG": "CLOG",
    "ALOG": "CLOG",
    "SIN": "CSIN",
    "COS": "CCOS",
}

# F77 lexical-comparison intrinsics (X3.9-1978 15.10): compare two CHARACTER values on the
# ASCII collating sequence, blank-padded to equal length, returning a logical.
_CHAR_LOGICAL = {
    "LGE": lambda a, b: a >= b,
    "LGT": lambda a, b: a > b,
    "LLE": lambda a, b: a <= b,
    "LLT": lambda a, b: a < b,
}

# The intrinsic library splits into three tiers, gated independently by the dialect so a strict
# dialect exposes only what it should (see engine._apply_intrinsic and dialect.py):
#   * _F66_INTRINSICS -- the ANSI X3.9-1966 library: Table 3 (intrinsic) + Table 4 (basic
#     external), 55 functions. Always available.
#   * _F77_INTRINSICS -- the ANSI X3.9-1978 additions (generic LOG/MAX/MIN, TAN/ASIN/ACOS/SINH/
#     COSH, the D... double specifics, NINT/ANINT, DPROD/DDIM, and the CHARACTER intrinsics
#     LEN/CHAR/ICHAR/INDEX + LGE/LGT/LLE/LLT). Gated on `f77_intrinsics` (F77 and FORTRAN10).
#   * _DEC_INTRINSICS -- everything else in INTRINSICS: the DEC-only functions (LSH/ROT, the
#     degree-argument trig TAND/SIND/..., the DOUBLE COMPLEX helpers DCMPLX/DIMAG/CD..., FLOATR/
#     DFLOAT/TIM2GO). Gated on `dec_library` (FORTRAN10 only). Computed below, after INTRINSICS.
_F66_INTRINSICS = frozenset(
    # Table 3 (31 intrinsic functions)
    "ABS IABS DABS AINT INT IDINT AMOD MOD AMAX0 AMAX1 MAX0 MAX1 DMAX1 AMIN0 AMIN1 MIN0 "
    "MIN1 DMIN1 FLOAT IFIX SIGN ISIGN DSIGN DIM IDIM SNGL REAL AIMAG DBLE CMPLX CONJG "
    # Table 4 (24 basic external functions)
    "EXP DEXP CEXP ALOG DLOG CLOG ALOG10 DLOG10 SIN DSIN CSIN COS DCOS CCOS TANH SQRT "
    "DSQRT CSQRT ATAN DATAN ATAN2 DATAN2 DMOD CABS".split()
)
# ANSI X3.9-1978 (FORTRAN 77) additions beyond the F66 library. The CHARACTER intrinsics
# (LEN/CHAR/ICHAR/INDEX, LGE/LGT/LLE/LLT) are listed here but also need the character_type dialect.
_F77_INTRINSICS = frozenset(
    "LOG LOG10 MAX MIN TAN ASIN ACOS SINH COSH NINT ANINT IDNINT DNINT DINT DTAN DASIN DACOS "
    "DSINH DCOSH DTANH DDIM DPROD LEN CHAR ICHAR INDEX LGE LGT LLE LLT".split()
)


def _re(x):
    """The value as a real -- a COMPLEX contributes its real part. FORTRAN INT/REAL/AINT/... of a
    COMPLEX argument are defined as the operation on REAL(z) (X3.9-1978 Table 5)."""
    return x.real if isinstance(x, complex) else x


INTRINSICS = {
    # ---- DEC extensions ----
    "LSH": lambda a: _lsh(PDP10, a[0], a[1]),  # width-dependent; routed via self.tgt
    "ROT": lambda a: _rot(PDP10, a[0], a[1]),  # width-dependent; routed via self.tgt
    # ---- type conversion (INT-family wrap applied target-aware in _apply_intrinsic) ----
    "INT": lambda a: int(_re(a[0])),  # INT of a COMPLEX truncates its real part
    "IFIX": lambda a: int(_re(a[0])),
    "IDINT": lambda a: int(_re(a[0])),
    "FLOAT": lambda a: float(_re(a[0])),
    "FLOATR": lambda a: float(_re(a[0])),
    "SNGL": lambda a: float(_re(a[0])),
    "REAL": lambda a: a[0].real if isinstance(a[0], complex) else float(a[0]),
    # ---- COMPLEX (V5 Ch4/Table 15-1; values are Python complex) ----
    "CMPLX": lambda a: complex(a[0], a[1] if len(a) > 1 else 0.0),
    "DCMPLX": lambda a: complex(a[0], a[1] if len(a) > 1 else 0.0),
    "AIMAG": lambda a: a[0].imag if isinstance(a[0], complex) else 0.0,
    "DIMAG": lambda a: a[0].imag if isinstance(a[0], complex) else 0.0,  # imag part of DBLE COMPLEX
    "DREAL": lambda a: a[0].real if isinstance(a[0], complex) else float(a[0]),  # DBLE CPLX real
    "CONJG": lambda a: a[0].conjugate() if isinstance(a[0], complex) else complex(a[0]),
    "DCONJG": lambda a: a[0].conjugate() if isinstance(a[0], complex) else complex(a[0]),
    "CABS": lambda a: abs(a[0]),
    "CDABS": lambda a: abs(a[0]),  # DOUBLE COMPLEX modulus
    "CSQRT": lambda a: cmath.sqrt(a[0]),
    "CDSQRT": lambda a: cmath.sqrt(a[0]),
    "CEXP": lambda a: cmath.exp(a[0]),
    "CDEXP": lambda a: cmath.exp(a[0]),
    "CLOG": lambda a: cmath.log(a[0]),
    "CDLOG": lambda a: cmath.log(a[0]),
    "CSIN": lambda a: cmath.sin(a[0]),
    "CDSIN": lambda a: cmath.sin(a[0]),
    "CCOS": lambda a: cmath.cos(a[0]),
    "CDCOS": lambda a: cmath.cos(a[0]),
    "TIM2GO": lambda a: 1.0e9,  # CPU time remaining (V5 Table 15-2): effectively unlimited
    "DBLE": lambda a: float(_re(a[0])),
    "AINT": lambda a: float(int(_re(a[0]))),  # truncate toward zero
    "ANINT": lambda a: _anint(_re(a[0])),
    "NINT": lambda a: int(_anint(_re(a[0]))),
    # ---- absolute value / sign / difference ----
    "ABS": lambda a: abs(a[0]),
    "IABS": lambda a: abs(int(a[0])),
    "DABS": lambda a: abs(a[0]),
    "SIGN": lambda a: abs(a[0]) if a[1] >= 0 else -abs(a[0]),
    "ISIGN": lambda a: abs(int(a[0])) if a[1] >= 0 else -abs(int(a[0])),
    "DSIGN": lambda a: abs(a[0]) if a[1] >= 0 else -abs(a[0]),
    "DIM": lambda a: max(a[0] - a[1], 0),
    "IDIM": lambda a: max(int(a[0]) - int(a[1]), 0),
    # ---- remaindering ----
    "MOD": lambda a: fort_mod(a[0], a[1]),
    "AMOD": lambda a: fort_mod(float(a[0]), float(a[1])),
    "DMOD": lambda a: fort_mod(float(a[0]), float(a[1])),
    # ---- max / min (all F66 typed variants + generic) ----
    "MAX0": lambda a: max(int(x) for x in a),
    "MIN0": lambda a: min(int(x) for x in a),
    "MAX1": lambda a: int(max(float(x) for x in a)),
    "MIN1": lambda a: int(min(float(x) for x in a)),
    "AMAX0": lambda a: float(max(int(x) for x in a)),
    "AMIN0": lambda a: float(min(int(x) for x in a)),
    "AMAX1": lambda a: max(float(x) for x in a),
    "AMIN1": lambda a: min(float(x) for x in a),
    "MAX": lambda a: max(a),
    "MIN": lambda a: min(a),
    # ---- square root / exponential / logarithm ----
    "SQRT": lambda a: math.sqrt(a[0]),
    "DSQRT": lambda a: math.sqrt(a[0]),
    "EXP": lambda a: math.exp(a[0]),
    "DEXP": lambda a: math.exp(a[0]),
    "ALOG": lambda a: math.log(a[0]),
    "DLOG": lambda a: math.log(a[0]),
    "ALOG10": lambda a: math.log10(a[0]),
    "DLOG10": lambda a: math.log10(a[0]),
    "LOG": lambda a: math.log(a[0]),  # F77 generic natural log (F66 spelled it ALOG)
    "LOG10": lambda a: math.log10(a[0]),  # F77 generic common log (F66: ALOG10)
    # ---- F77 CHARACTER (operands/results are Python str under the character_type dialect) ----
    "LEN": lambda a: len(a[0]),  # declared length (fixed-length vars are stored blank-padded)
    "CHAR": lambda a: chr(int(a[0]) & 0x7F),  # ASCII code -> the 1-character string
    "ICHAR": lambda a: ord(a[0][0]) if a[0] else 0,  # 1st char -> its ASCII code
    "INDEX": lambda a: a[0].find(a[1]) + 1,  # 1-based position of a[1] in a[0] (0 = not found)
    # ---- trigonometric / hyperbolic ----
    "SIN": lambda a: math.sin(a[0]),
    "DSIN": lambda a: math.sin(a[0]),
    "COS": lambda a: math.cos(a[0]),
    "DCOS": lambda a: math.cos(a[0]),
    "TAN": lambda a: math.tan(a[0]),
    "ATAN": lambda a: math.atan(a[0]),
    "DATAN": lambda a: math.atan(a[0]),
    "ATAN2": lambda a: math.atan2(a[0], a[1]),
    "DATAN2": lambda a: math.atan2(a[0], a[1]),
    "SINH": lambda a: math.sinh(a[0]),
    "COSH": lambda a: math.cosh(a[0]),
    "TANH": lambda a: math.tanh(a[0]),
    "SIND": lambda a: math.sin(math.radians(a[0])),  # sine of degrees
    "COSD": lambda a: math.cos(math.radians(a[0])),  # cosine of degrees
    "ASIN": lambda a: math.asin(a[0]),
    "ACOS": lambda a: math.acos(a[0]),
    "DTAN": lambda a: math.tan(a[0]),
    "DASIN": lambda a: math.asin(a[0]),
    "DACOS": lambda a: math.acos(a[0]),
    "DSINH": lambda a: math.sinh(a[0]),
    "DCOSH": lambda a: math.cosh(a[0]),
    "DTANH": lambda a: math.tanh(a[0]),
    # ---- degree-argument trig (V5): argument/result in degrees ----
    "TAND": lambda a: math.tan(math.radians(a[0])),
    "ASIND": lambda a: math.degrees(math.asin(a[0])),
    "ACOSD": lambda a: math.degrees(math.acos(a[0])),
    "ATAND": lambda a: math.degrees(math.atan(a[0])),
    "ATAN2D": lambda a: math.degrees(math.atan2(a[0], a[1])),
    "DSIND": lambda a: math.sin(math.radians(a[0])),
    "DCOSD": lambda a: math.cos(math.radians(a[0])),
    "DTAND": lambda a: math.tan(math.radians(a[0])),
    # ---- double-precision variants (we model double as Python float) ----
    "DFLOAT": lambda a: float(a[0]),  # integer -> double
    "DINT": lambda a: float(int(a[0])),  # truncate toward zero
    "DNINT": lambda a: _anint(a[0]),  # round to nearest whole
    "IDNINT": lambda a: int(_anint(a[0])),  # round to nearest integer
    "DDIM": lambda a: max(a[0] - a[1], 0),  # positive difference
    "DPROD": lambda a: float(a[0]) * float(a[1]),  # double product of two reals
    "DMAX1": lambda a: max(float(x) for x in a),
    "DMIN1": lambda a: min(float(x) for x in a),
}

# The DEC-only tier: every intrinsic past the F66 + F77 libraries (LSH/ROT, the degree-argument
# trig, the DOUBLE COMPLEX helpers, FLOATR/DFLOAT/TIM2GO). Gated on `dec_library` (FORTRAN10).
_DEC_INTRINSICS = frozenset(
    k for k in INTRINSICS if k not in _F66_INTRINSICS and k not in _F77_INTRINSICS
)
