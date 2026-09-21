"""
Python port of parse_network's make_derivs(), add_defs_todefsh(), and
make_voltage_clamp_I() -- the stage that turns a finished CfgCompiler
(from codegen.py) plus the merged .par text into the final generated
files: defs.h, globalvars.h, derivs.h, prototypes.h, init.h, derivs.c,
inf_tau.c.
"""
from __future__ import annotations
from .codegen import CfgCompiler
from . import pars


def _split_globals(globals_lines: list[str]) -> tuple[list[str], list[str]]:
    """grep '^int ' / grep '^double ' over the first-pass globalvars.h lines."""
    int_lines = [l for l in globals_lines if l.startswith("int ")]
    double_lines = [l for l in globals_lines if l.startswith("double ")]
    return int_lines, double_lines


def _index_doubles(double_lines: list[str]) -> tuple[list[str], list[str]]:
    names, vals = [], []
    for ln in double_lines:
        s = ln.rstrip("\n")
        if s.endswith(";"):
            s = s[:-1]
        toks = s.split()
        # toks == ["double", NAME, "=", VAL]
        names.append(toks[1])
        vals.append(toks[-1])
    return names, vals


def generate(cfg_text: str, par_text: str) -> dict[str, str]:
    """
    Full "network project" parse: equivalent of
        define_vars_pars; make_inf_tau_file; make_derivs;
        add_defs_todefsh; make_voltage_clamp_I
    Returns a dict of {filename: content} for defs.h, globalvars.h,
    derivs.h, prototypes.h, init.h, derivs.c, inf_tau.c, plus
    ".networkpars" (so a first run doesn't require a separate -r pass).
    par_text and cfg_text should be RAW (with comments); comment-stripping
    (including #define passthrough capture) happens here, matching the
    original remove_comments() call that precedes define_vars_pars().
    """
    stripped_cfg, cfg_defines = pars.strip_comments(cfg_text)
    stripped_par, par_defines = pars.strip_comments(par_text)

    from .codegen import parse_cfg_text
    comp, num_odes = parse_cfg_text(stripped_cfg)

    inf_tau_c = pars.make_inf_tau_file(stripped_par, cadep_names=comp.tmpca)

    int_lines, double_lines = _split_globals(comp.globals)
    names, vals = _index_doubles(double_lines)

    defs_b1 = []
    for i, name in enumerate(names):
        defs_b1.append(f"#define {name} P[{i}]\n")
    defs_b1.append(f"#define NUM_DOUBLES {len(names)}\n")

    n_array = "char N[{}][LEN]={{{}}};\n".format(
        len(names), ", ".join(f'"{n}"' for n in names)
    )
    p_array = "double P[NUM_DOUBLES] = {{{}}};\n".format(
        ", ".join(f"{float(v):.6f}" for v in vals)
    )
    vc_indices = [i for i, name in enumerate(names) if "Vm" in name]

    keep_init = comp.tmpg1 if comp.num_keep > 0 else ""

    globalvars_h = (
        "// Globals\n"
        + '#include "defs.h"\n'
        + "".join(int_lines)
        + n_array
        + p_array
        + keep_init
        + "extern int First;\n"
    )

    defs_h = "".join(comp.defs) + "".join(defs_b1) + "#define PI 3.141592654\n"

    # ---- Verbatim block -----------------------------------------------
    verbatim_lines = []
    for ln in stripped_par.splitlines():
        fields = ln.split()
        if not fields:
            continue
        if fields[0] == "V" or fields[0].lower() == "verbatim":
            verbatim_lines.append((fields[0], ln))

    if verbatim_lines:
        defs_h += "#define VERBATIM\n"
        inith_verbatim_proto = "void Verbatim(double t, int i, double *Y);\n"
        vb = ["void Verbatim(double t, int i, double *Y)\n{\n"]
        for marker, ln in verbatim_lines:
            rest = ln.replace(marker, "", 1)
            vb.append(f"\t{rest}\n")
        vb.append("}\n")
        verbatim_c = "".join(vb)
    else:
        inith_verbatim_proto = ""
        verbatim_c = ""

    # ---- init_derivs() body (power-line assignments + .networkpars loader) --
    power_lines = pars.extract_power_lines(stripped_par)
    networkpars = pars.get_pars(stripped_par)

    init_derivs_lines = [
        "void init_derivs(void)\n{\n",
        "FILE *fp;\n",
        "int i;\n",
        "double val;\n",
        "char name[256];\n",
    ]
    for pl in power_lines:
        init_derivs_lines.append(f"\t{pl};\n")
    init_derivs_lines += [
        '\n\tfp=fopen(".networkpars","r");\n\n',
        '\twhile(fscanf(fp, "%s %lf", name, &val) != EOF)\n',
        "\t{\n",
        "\t\tfor(i=0;i<=NUM_DOUBLES;i++)\n",
        "\t\t\tif(strcmp(name,N[i]) == 0)\n",
        "\t\t\t\tP[i]=val;\n",
        "\t}\n",
        "\n\tfclose(fp);\n",
        "}\n",
    ]

    # ---- derivs() dispatcher -------------------------------------------
    derivs_dispatch = ["void derivs(double t, double *yin, double *yout)\n{\n"]
    derivs_dispatch.append("#ifdef NODES\n\tupdate_nodes(t,yin);\n#endif\n")
    for i in range(num_odes):
        derivs_dispatch.append(f"\tyout[{i}] = RHS{i}(t, yin);\n")
    derivs_dispatch.append("}\n")

    # ---- assemble derivs.c ----------------------------------------------
    derivs_c = (
        "#include <stdio.h>\n"
        "#include <stdlib.h>\n"
        "#include <string.h>\n"
        "#include <math.h>\n"
        '#include "defs.h"\n'
        '#include "globalvars.h"\n'
        '#include "prototypes.h"\n'
        '#include "numtools.h"\n'
        "////////////////////////////////////\n"
        + "".join(init_derivs_lines)
        + "////////////////////////////////////\n"
        + "".join(comp.bufV1)
        + "////////////////////////////////////\n"
        + "".join(comp.m1)
        + "////////////////////////////////////\n"
        + "".join(derivs_dispatch)
        + "////////////////////////////////////\n"
        + verbatim_c
        + "////////////////////////////////////\n"
        + "".join(comp.bufNd1)
        + "////////////////////////////////////\n"
    )

    # ---- init.h (add_defs_todefsh) --------------------------------------
    y_names = [n for n in _extract_define_names(defs_h, "Y[")]
    g_names = [n for n in _extract_define_names(defs_h, "G[")]

    init_h_parts = []
    init_h_parts.append(
        "char *Vars[]={{{}}};\n".format(", ".join(f'"{n}"' for n in y_names))
    )
    if g_names:
        init_h_parts.append(
            "char *Keeps[]={{{}}};\n".format(", ".join(f'"{n}"' for n in g_names))
        )
    if vc_indices:
        init_h_parts.append(
            "int VC_num[NUMVCS]={{{}}};\n".format(
                ", ".join(str(i) for i in vc_indices)
            )
        )
    init_h_parts.append("int First=TRUE;\n")
    init_h_parts.append(inith_verbatim_proto)
    init_h = "".join(init_h_parts)

    prototypes_h = "".join(comp.prototypes)
    if comp.num_nodes > 0:
        prototypes_h += "void update_nodes(double t, double *Y);\n"

    derivs_h = "".join(comp.derivs_h)

    # ---- make_voltage_clamp_I --------------------------------------------
    if comp.num_vcs > 0:
        vclamp_c = ["void vclampI(double t, double *yin, double *vci)\n{\n"]
        for i in range(comp.num_vcs):
            vclamp_c.append(f"\tvci[{i}] = -1.0*VClampI{i}(t, yin);\n")
        vclamp_c.append("}\n")
        derivs_c += "".join(vclamp_c)
        derivs_h += "".join(comp.tmpprotovc)

    # ---- #define passthrough (par then cfg, per original order) ----------
    defs_h += "".join(l + "\n" for l in (par_defines + cfg_defines))

    return {
        "defs.h": defs_h,
        "globalvars.h": globalvars_h,
        "derivs.h": derivs_h,
        "prototypes.h": prototypes_h,
        "init.h": init_h,
        "derivs.c": derivs_c,
        "inf_tau.c": inf_tau_c,
        ".networkpars": networkpars,
    }


def _extract_define_names(defs_h_text: str, marker: str) -> list[str]:
    """grep 'Y[' / grep 'G[' defs.h, then take $2 of each '#define NAME marker...' line."""
    names = []
    for ln in defs_h_text.splitlines():
        if marker in ln and ln.startswith("#define "):
            toks = ln.split()
            if len(toks) >= 3:
                names.append(toks[1])
    return names


def rerun_pars(par_text: str) -> str:
    """Equivalent of `network`'s runcmd()/`-r` path: remove_par_comments;
    get_pars -- used to regenerate .networkpars without recompiling."""
    stripped_par, _ = pars.strip_comments(par_text)
    return pars.get_pars(stripped_par)
