"""
Python port of tabulate_network. Only invoked when the user asks for the
lookup-table optimization (equivalent of the original `-tabulate`/`-t`
flag). Reads a compiled inf_tau.c (functions of the form
`double NAME(double x) { return (EXPR); }`), and:
  1. produces inf_tau_tables.h: a big C array per function, precomputed at
     every integer voltage from Vmin=-150+perturb to Vmax=150+perturb.
  2. rewrites inf_tau.c so each function does table lookup + linear
     interpolation instead of evaluating EXPR every call.

Note: this only handles the non-Ca-dependent `double NAME(double x)`
functions, exactly like the original (Ca-dependent `(double x, double ca)`
functions are not parsed by tabulate_network's `double `/`return ` scan
in a way that captures the second argument, so they pass through
unmodified -- same limitation as upstream).
"""
from __future__ import annotations
import re

_FUNC_RE = re.compile(r"double\s+(\w+)\s*\(")
_RETURN_RE = re.compile(r"return\s*\((.*)\)\s*;")


def tabulate(inf_tau_c: str, perturb: float = 0.0) -> tuple[str, str]:
    """Returns (new_inf_tau_c, inf_tau_tables_h)."""
    names: list[str] = []
    exprs: list[str] = []

    fname = None
    for line in inf_tau_c.splitlines():
        m = _FUNC_RE.search(line)
        if line.startswith("double ") and m:
            fname = m.group(1)
            continue
        if line.strip().startswith("return") and fname is not None:
            m2 = _RETURN_RE.search(line)
            if m2:
                names.append(fname)
                exprs.append(m2.group(1))

    vmin = -150.0 + perturb
    vmax = 150.0 + perturb
    vmin_i, vmax_i = int(vmin), int(vmax)

    # Evaluate each expression at integer x from vmin to vmax (inclusive),
    # mirroring the awk-generated-awk evaluator's `for(x=Vmin;x<Vmax;x++)`
    # loop plus the one extra point at x==Vmax appended after.
    import math

    def c_eval(expr: str, x: float) -> float:
        env = {
            "exp": math.exp, "tanh": math.tanh, "sqrt": math.sqrt,
            "log": math.log, "sin": math.sin, "cos": math.cos,
            "pow": math.pow, "fabs": abs,
            "min": min, "max": max, "absVal": abs,
            "x": x, "V": x, "v": x, "X": x,
        }
        return eval(expr, {"__builtins__": {}}, env)  # noqa: S307 (trusted, local codegen input)

    # new_inf_tau_c: #include + defines + the lookup functions themselves
    # (this REPLACES inf_tau.c). inf_tau_tables_h: the raw precomputed
    # double NAME_Array[...] = {...}; data, #included by new_inf_tau_c.
    new_c_lines = [
        '#include "inf_tau_tables.h"\n',
        "#define V x\n",
        "#define v x\n",
        "#define X x\n",
        f"#define VMIN {vmin_i}\n",
        f"#define VMAX {vmax_i}\n",
    ]
    array_defs = []
    for name, expr in zip(names, exprs):
        vals = [c_eval(expr, float(x)) for x in range(vmin_i, vmax_i)]
        vals.append(c_eval(expr, float(vmax_i)))
        arr = ", ".join(f"{v:.6f}" for v in vals)
        array_defs.append(f"double {name}_Array[{vmax_i - vmin_i + 1}]={{{arr}}};\n")

        new_c_lines.append(f"//\ndouble {name}(double x)\n{{\n")
        new_c_lines.append("int i;\n")
        new_c_lines.append(f"\tif(x<=VMIN) return ({name}_Array[0]);\n")
        new_c_lines.append(f"\telse if(x>=VMAX) return ({name}_Array[VMAX-VMIN]);\n")
        new_c_lines.append("\telse {\n")
        new_c_lines.append("\t   i=(x<0)?((int) x-VMIN-1):((int) x-VMIN);\n")
        new_c_lines.append(
            f"\t   return ( {name}_Array[i]+({name}_Array[i+1]-{name}_Array[i])"
            "*(x-i-VMIN) );\n"
        )
        new_c_lines.append("\t}\n}\n")

    new_inf_tau_c = "".join(new_c_lines)
    inf_tau_tables_h = "".join(array_defs)
    return new_inf_tau_c, inf_tau_tables_h
