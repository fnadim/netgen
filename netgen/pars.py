"""
Python port of the .par-file-level bash/gawk functions in parse_network:
remove_par_comments/remove_cfg_comments, get_pars, make_inf_tau_file, and
the "power line" extraction used by make_derivs()'s init_derivs() codegen.

All functions here operate on already comment-stripped text (parse_network
always calls remove_comments() before these run) unless noted otherwise.
"""
from __future__ import annotations
import re

# egrep pattern from get_pars(): matches lines containing any of these
# (word-boundary) substrings anywhere in the line.
_GETPARS_RE = re.compile(
    r"(_Gmax\b|_Erev\b|_Iext\b|_Cm\b|_Vm\b|_Ga\b|_Ggap\b|power\b|_AlphaTau\b|"
    r"_Period\b|_Tolerance\b|_Duration\b|_Amplitude\b|_Threshold\b|_Delay\b|"
    r"_Above\b|_frac\b|__\b)"
)


def strip_comments(text: str) -> tuple[str, list[str]]:
    """
    Port of remove_par_comments/remove_cfg_comments (same logic, used for
    both .cfg and .par text). For each non-blank line, split on '#'; the
    code part (field 1) is kept for further parsing. If the comment part's
    first whitespace-token is exactly "define", the WHOLE ORIGINAL LINE is
    also captured (later spliced verbatim into defs.h) -- this is the
    "#define passthrough" feature from README v1.47.
    Returns (stripped_text, define_passthrough_lines).
    """
    code_lines: list[str] = []
    passthrough: list[str] = []
    for raw in text.splitlines():
        if raw.strip() == "":
            continue
        parts = raw.split("#", 1)
        code_lines.append(parts[0])
        if len(parts) > 1 and parts[1] != "":
            comment_fields = parts[1].split()
            if comment_fields and comment_fields[0] == "define":
                passthrough.append(raw)
    return "\n".join(code_lines), passthrough


def _getpars_candidates(par_text: str) -> list[str]:
    return [ln for ln in par_text.splitlines() if _GETPARS_RE.search(ln)]


def extract_power_lines(par_text: str) -> list[str]:
    """Port of `grep "power\\b" tmpp0` (tmpin): candidate lines containing
    the word "power". Returned as raw "NAME=VALUE" text, used verbatim as
    C assignment statements inside init_derivs()."""
    return [ln for ln in _getpars_candidates(par_text) if re.search(r"power\b", ln)]


def get_pars(par_text: str) -> str:
    """
    Port of get_pars(): build the "NAME VALUE\\n"... content of
    .networkpars from the comment-stripped merged .par text.

    Faithfully reproduces the two-pass awk filter:
      pass 1: candidate lines whose first whitespace-token does NOT start
              with "V" (this excludes Verbatim-block lines, which start
              with a lone "V" token) and which do NOT contain "power"
              anywhere (power is compiled in, not runtime-settable).
      pass 2: candidate lines whose first token contains "V" anywhere AND
              "__" (re-admits V-prefixed *global* variable names, which
              pass 1's blanket "starts with V" exclusion would otherwise
              wrongly drop -- these must end in "__" per the DSL's global
              variable convention). May duplicate a pass-1 line; harmless,
              since .networkpars is read as repeated name/value pairs.
    """
    candidates = _getpars_candidates(par_text)
    out_lines: list[str] = []

    def emit(ln: str):
        transformed = ln.replace("=", " ")
        toks = transformed.split()
        if len(toks) < 2:
            return
        name, val = toks[0], toks[1]
        name = name.replace("_Ggap", "_Gmax")
        out_lines.append(f"{name} {val}")

    for ln in candidates:
        first_tok = ln.split(None, 1)[0] if ln.split(None, 1) else ln
        if "power" in ln:
            continue
        if first_tok.startswith("V"):
            continue
        emit(ln)

    for ln in candidates:
        first_tok = ln.split(None, 1)[0] if ln.split(None, 1) else ln
        if "V" in first_tok and "__" in first_tok:
            emit(ln)

    return "\n".join(out_lines) + ("\n" if out_lines else "")


def make_inf_tau_file(par_text: str, cadep_names: list[str] | None = None) -> str:
    """
    Port of make_inf_tau_file(): for every "NAME=EXPR" line in the
    (comment-stripped) merged .par text where NAME contains "inf", "tau",
    "alpha", or "beta", emit a C function
        double NAME(double x[, double ca | double ica]) { return (EXPR); }

    This is a faithful two-pass port (the original really does run this as
    two separate gawk passes over the generated function text):

    Pass 1 (awk lines 997-1004 of parse_network): a function whose NAME
    contains "Cainf" or "Catau" (the auto-generated per-cell calcium-pool
    ODE functions from codegen.Make_dCa) gets a second parameter named
    "ica" (the summed calcium CURRENT, matching how those bodies use
    "ica"/"ICa"/etc. -- see the #define block below). Every other function
    gets a single "double x" parameter at this stage.

    Pass 2 (awk lines 1008-1021): separately, any function whose NAME is
    one of `cadep_names` (codegen.CfgCompiler.tmpca -- the
    CELL_CURR_minf/mtau names of currents carrying a CaXDep modifier in
    the .cfg, e.g. a KCa current) -- or, as a rarely-used manual escape
    hatch, whose generated line literally contains the word "cadep" -- has
    its (still-single) "double x" parameter widened to "double x, double
    ca" (the calcium CONCENTRATION, not the current -- a different
    parameter from pass 1's "ica"). The original applies this as a
    textual `sub("double x", ...)` over every emitted line, which in
    practice only ever matches a function's own signature line (the only
    line containing both its name and the literal text "double x") -- so
    that's what this does too, checked per generated line rather than per
    parsed name/expr pair.
    """
    cadep_names = cadep_names or []
    funcs: list[tuple[str, str]] = []
    for line in par_text.splitlines():
        if "=" not in line:
            continue
        name, expr = line.split("=", 1)
        name, expr = name.strip(), expr.strip()
        if name and any(k in name for k in ("inf", "tau", "alpha", "beta")):
            funcs.append((name, expr))

    header = [
        '#include "defs.h"',
        "#include <math.h>",
        "#define V x",
        "#define v x",
        "#define X x",
        "#define ICa ica",
        "#define Ica ica",
        "#define iCa ica",
        "#define ICA ica",
        "#define Ca ca",
        "#define CA ca",
        "#define min(X, Y) (((X) < (Y)) ? (X):(Y))",
        "#define max(X, Y) (((X) > (Y)) ? (X):(Y))",
        "#define absVal(X) (((X) > 0) ? (X):-(X))",
        "extern double P[];",
    ]
    out_lines = [line + "\n" for line in header]

    # pass 1: emit each function as its 4 physical lines (signature, "{",
    # return, "}"), since pass 2's substitution operates per physical line.
    pass1_lines: list[str] = []
    for name, expr in funcs:
        var = "double x, double ica" if ("Cainf" in name or "Catau" in name) else "double x"
        pass1_lines.append(f"double {name}({var})\n")
        pass1_lines.append("{\n")
        pass1_lines.append(f"\treturn ({expr});\n")
        pass1_lines.append("}\n")

    # pass 2
    cadep_set = set(n.strip() for n in cadep_names if n.strip())
    for line in pass1_lines:
        is_cadep = any(v in line for v in cadep_set) or "cadep" in line.lower()
        if is_cadep:
            line = line.replace("double x", "double x, double ca", 1)
        out_lines.append(line)

    return "".join(out_lines)
