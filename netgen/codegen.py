"""
Python port of `parse_network` (the gawk-based cfg parser / C code generator)
from network_2_11. This is a function-for-function transliteration of the
gawk script embedded in `define_vars_pars()`, preserving variable names,
buffer names, and assembly order so the generated C is behaviorally
equivalent to the original.

Dead code from the original (Write_dVm, wex, Make_dmh_alphabeta1) is not
ported since it has no call sites in parse_network.
"""
from __future__ import annotations
from dataclasses import dataclass, field


TRUE = 1
FALSE = 0


class CfgCompiler:
    """
    Consumes the (comment-stripped) lines of a .cfg file, one at a time via
    process_line(), then finalize() to close out. Produces the same set of
    generated-file fragments that parse_network's awk script produces:
    defs.h, globalvars.h (first pass, pre-make_derivs), prototypes.h,
    derivs.h, and the derivs.c body pieces (per-cell RHS functions, per-gate
    ODE RHS functions, node-update code, voltage-clamp code).
    """

    def __init__(self):
        # Output text accumulators, mirroring the awk script's file handles.
        self.prototypes: list[str] = ["// Inf & Tau Prototypes\n"]
        self.derivs_h: list[str] = ["// Derivs Prototypes\n"]
        self.defs: list[str] = ["// Defs file\n", "#define LEN 256\n"]
        self.globals: list[str] = []  # first-pass globalvars.h content

        # Per-cell scratch buffers (awk: tmpV1<cell> etc.)
        self.V1: dict[str, list[str]] = {}
        self.V2: dict[str, list[str]] = {}
        self.V3: dict[str, list[str]] = {}
        self.V4: dict[str, list[str]] = {}
        self.V6ca: dict[str, list[str]] = {}   # fca: ICa accumulation
        self.tmpddd: dict[str, str] = {}       # depressing-synapse extra decls (reset each call)

        # Per-node scratch buffers (awk: tmpNd1<node>/tmpNd2<node>)
        self.Nd1: dict[str, list[str]] = {}
        self.Nd2: dict[str, list[str]] = {}

        # Global accumulator buffers, assembled in Write_cell/Write_node/Write_vclamp
        self.bufV1: list[str] = []       # final derivs.c cell-RHS bodies (awk: bare "tmpV1")
        self.bufNd1: list[str] = []      # final node-update code (awk: bare "tmpNd1")
        self.m1: list[str] = []          # gate (m/h/Ca) RHS functions (awk: tmpm1 -> fmh1)
        self.tmpca: list[str] = []       # names of cadep inf/tau functions (awk: tmpca)
        self.tmpprotovc: list[str] = []  # voltage-clamp current prototypes

        # Parser state
        self.cell: str | None = None
        self.curr: str | None = None
        self.syn: str | None = None
        self.cellpre: str | None = None
        self.token: str | None = None
        self.object: str | None = None
        self.keep = False
        self.cadep = 0
        self.Depress = False
        self.FirstCa: dict[str, bool] = {}

        self.cl: list[str] = []          # ordered list of (non-vclamp) cell names
        self.ode: list[int] = []         # starting num_odes index for each cell (parallel to cl)
        self.vcl: list[str] = []         # ordered list of voltage-clamped cell names
        self.node_name: list[str] = []

        self.num_odes = 0
        self.old_num_odes = 0
        self.num_keep = 0
        self.num_cells = 0
        self.num_vcs = 0
        self.num_nodes = 0
        self.First = True
        self.FirstVC = True

        self.type: list[str] = []   # per-ode-index: "Vm" | "Ca" | "mh"
        self.dmh: dict[int, str] = {}  # per-ode-index RHS expression text (gate/Ca odes)

    # ---- small buffer helpers -------------------------------------------------
    def _v1(self, cell):
        return self.V1.setdefault(cell, [])

    def _v2(self, cell):
        return self.V2.setdefault(cell, [])

    def _v3(self, cell):
        return self.V3.setdefault(cell, [])

    def _v4(self, cell):
        return self.V4.setdefault(cell, [])

    def _vca(self, cell):
        return self.V6ca.setdefault(cell, [])

    def _nd1(self, node):
        return self.Nd1.setdefault(node, [])

    def _nd2(self, node):
        return self.Nd2.setdefault(node, [])

    # ---- awk function ports -----------------------------------------------
    def Write_I_in_ICa(self, cell, depcurr, n):
        if n == 0:
            self._vca(cell).append(f"\t{cell}_ICa = 0.0;\n")
        else:
            self._vca(cell).append(f"\t{cell}_ICa += {cell}_{depcurr}_I;\n")

    def Write_Gmax_Erev(self, c, curr):
        self.globals.append(f"double {c}_{curr}_Gmax = 0;\n")
        self.globals.append(f"double {c}_{curr}_Erev = 0;\n")

    def Write_keep(self, ce, cu, name):
        if cu != "":
            self.defs.append(f"#define {ce}_{cu}_{name} G[{self.num_keep}]\n")
        else:
            self.defs.append(f"#define {ce}_{name} G[{self.num_keep}]\n")
        self.num_keep += 1

    def add_global2pars(self, name):
        self.globals.append(f"double {name} = 0;\n")

    def Write_Ggap(self, s):
        self.globals.append(f"double {s}_{self.curr}_Gmax = 0;\n")
        self.globals.append(f"double {s}_{self.curr}_frac = 0;\n")

    def Write_cell_pars(self, name):
        val = 1 if name in ("Cm", "Ga") else 0
        self.globals.append(f"double {self.cell}_{name} = {val};\n")

    def Write_power(self, m_or_h):
        self.globals.append(f"int {self.cell}_{self.curr}_{m_or_h}power = 0;\n")

    def Write_Global(self, name, val, c, curr):
        self.globals.append(f"double {c}_{curr}_{name} = {val};\n")

    def Write_Global_Vm(self, c, val):
        self.globals.append(f"double {c}_Vm = {val};\n")

    def Write_Global_Vnode(self, c, val):
        self.globals.append(f"double {c}_Vnode = {val};\n")

    def Write_prototype(self, c, func_name):
        varin = "double x, double ca" if self.cadep else "double x"
        self.prototypes.append(f"double {c}_{self.curr}_{func_name}({varin});\n")

    def Write_ca_prototype(self, c, func_name):
        self.prototypes.append(f"double {c}_{func_name}(double x, double ica);\n")

    def Write_vars_in_defs(self, c, name):
        if name in ("Vm", "Ca"):
            while len(self.type) <= self.num_odes:
                self.type.append("")
            self.type[self.num_odes] = name
            self.defs.append(f"#define {c}_{name} Y[{self.num_odes}]\n")
        else:
            while len(self.type) <= self.num_odes:
                self.type.append("")
            self.type[self.num_odes] = "mh"
            self.defs.append(f"#define {c}_{self.curr}_{name} Y[{self.num_odes}]\n")
        self.num_odes += 1

    def string_mult(self, b, cell):
        if "inf" in b:
            v_or_null = f"({cell}_Vm)"
            b2 = "m"
        else:
            v_or_null = ""
            b2 = b
        self._v4(cell).append(
            f" * power({cell}_{self.curr}_{b}{v_or_null} , {cell}_{self.curr}_{b2}power)"
        )

    def syn_string_mult(self, b, cell):
        v_or_null = f"({self.cellpre}_Vm)" if "inf" in b else ""
        self._v4(cell).append(f" * {self.syn}_{self.curr}_{b}{v_or_null}")

    def syn_post_string_mult(self, b, cell):
        v_or_null = f"({cell}_Vm)" if "inf" in b else ""
        self._v4(cell).append(f" * {self.syn}_{self.curr}_{b}{v_or_null}")

    def Stick_Ipulse_in_dVm(self, c, curr):
        self._v1(self.cell).append(f"double {c}_{curr}_I;\n")
        self._v2(self.cell).append(
            f"\t{c}_{curr}_I = \\\n"
            f"\t    \tpulseStim({c}_{curr}_Period,{c}_{curr}_Duration,{c}_{curr}_Amplitude,t);\n"
        )
        self._v3(self.cell).append(f"+ {c}_{curr}_I ")

    def Stick_IControlled_in_dVm(self, c, curr):
        self._v1(self.cell).append(f"double {c}_{curr}_I;\n")
        self._v1(self.cell).append(f"double {c}_{curr}_IC;\n")
        v2 = self._v2(self.cell)
        v2.append(f"\t{c}_{curr}_I = pulseStim({c}_{curr}_Period,")
        v2.append(f"{c}_{curr}_Duration,{c}_{curr}_Amplitude,t);\n")
        v2.append(f"\t{c}_{curr}_IC = controlledPulse(t,{c}_{curr}_I,")
        v2.append(f"{self.cellpre}_Vm,{c}_{curr}_Threshold,{c}_{curr}_Delay,")
        v2.append(f"{c}_{curr}_Above);\n")
        self._v3(self.cell).append(f"+ {c}_{curr}_IC ")

    def Stick_I_in_dVm(self, c, curr):
        cell = self.cell
        if not self.keep:
            self._v1(cell).append(f"double {c}_{curr}_G, {c}_{curr}_I;\n")
        else:
            self._v1(cell).append("")
        # awk: print "//" > "tmpddd" cell  (TRUNCATES each call)
        self.tmpddd[cell] = "//\n"

        v2 = self._v2(cell)
        v2.append(f"\t{c}_{curr}_I = {c}_{curr}_G * ({self.cell}_Vm - {c}_{curr}_Erev);\n")
        self._v3(cell).append(f"- {c}_{curr}_I ")

        v4 = self._v4(cell)
        v1 = self._v1(cell)
        if self.token == "AlphaFunction":
            v1.append(f"static double last_spike={-1:.1f};\n")
            if self.cellpre == "NULL":
                v4.append("\tif(isIntegerMultiple(t,")
                v4.append(f"{c}_{curr}_Period,{c}_{curr}_Tolerance))\n")
            else:
                v4.append("\tif(threshold_crossed(")
                v4.append(f"{self.cellpre}_Vm,{c}_{curr}_Threshold,{c}_{curr}_Slope))\n")
            v4.append("\t\tlast_spike=t;\n")

        v4.append(f"\t{c}_{curr}_G = {c}_{curr}_Gmax")
        token = self.token
        if token == "mInst":
            self.string_mult("minf", cell)
        elif token in ("mTauInf", "mAlphaBeta"):
            self.string_mult("m", cell)
        elif token == "mInst_hTauInf":
            self.string_mult("minf", cell)
            self.string_mult("h", cell)
        elif token in ("mhTauInf", "mhAlphaBeta"):
            self.string_mult("m", cell)
            self.string_mult("h", cell)
        elif token == "GradedmInst":
            self.syn_string_mult("minf", cell)
        elif token == "GradedmTauInf":
            self.syn_string_mult("m", cell)
        elif token == "GradedmhTauInf":
            self.syn_string_mult("m", cell)
            if self.Depress:
                self.syn_string_mult("hD", cell)
                ddd = []
                ddd.append("static int increasing=1;\n")
                ddd.append(f"static double {c}_{curr}_hD = 0.0;\n")
                ddd.append(f"static double {c}_{curr}_oldh = 1.0;\n")
                ddd.append(
                    f"\tif(({c}_{curr}_h +1.e-6 < {c}_{curr}_oldh) && increasing) {{\n"
                )
                ddd.append(f"\t\t{c}_{curr}_hD = {c}_{curr}_h;\n")
                ddd.append("\t\tincreasing=0;\n\t}\n")
                ddd.append(f"\telse if(({c}_{curr}_h > {c}_{curr}_oldh+1.e-6)) {{\n")
                ddd.append("\t\tincreasing=1;\n\t}\n")
                ddd.append(f"\t{c}_{curr}_oldh = {c}_{curr}_h;\n\n")
                self.tmpddd[cell] = "".join(ddd)
            else:
                self.syn_string_mult("h", cell)
        elif token == "GradedmInst_mpostInst":
            self.syn_string_mult("minf", cell)
            self.syn_post_string_mult("mpostinf", cell)
        elif token == "GradedmTauInf_mpostTauInf":
            self.syn_string_mult("m", cell)
            self.syn_post_string_mult("mpost", cell)
        elif token == "AlphaFunction":
            v4.append(f"*AlphaSyn({c}_{curr}_AlphaTau, last_spike")
            v4.append(f",{c}_{curr}_Tolerance,t)")
        v4.append(";\n")

    def Stick_Iaxial_in_dVm(self, c1, c2):
        self._v1(c2).append(f"static double {c1}_{c2}_G, {c1}_{c2}_I;\n")
        self._v2(c2).append(f"\t{c1}_{c2}_I = {c1}_{c2}_G * ({c1}_Vm - {c2}_Vm);\n")
        self._v3(c2).append(f"+ {c1}_{c2}_I ")
        self._v4(c2).append(
            f"\tif(First)\n\t\t{c1}_{c2}_G = 2.0 * {c1}_Ga * {c2}_Ga / ({c1}_Ga + {c2}_Ga);\n"
        )

    def Stick_node_Iaxial_in_dVm(self, c1, nd):
        self._v1(c1).append(f"static double {c1}_{nd}_G, {c1}_{nd}_I;\n")
        self._v2(c1).append(f"\t{c1}_{nd}_I = {c1}_{nd}_G * ({c1}_Vm - {c1}_Vnode);\n")
        self._v3(c1).append(f"- {c1}_{nd}_I ")
        self._v4(c1).append(f"\tif(First)\n\t\t{c1}_{nd}_G = 2.0 * {c1}_Ga;\n")
        self._nd1(nd).append(f" + {c1}_Ga*{c1}_Vm ")
        self._nd2(nd).append(f" + {c1}_Ga ")

    def Stick_Igap_in_dVm(self, c1, c2, token):
        self._v1(c2).append(f"double {c1}_{c2}_Gap_I;\n")
        curr = self.curr
        self._v2(c2).append(
            f"\t{c1}_{c2}_Gap_I = {c1}_{c2}_{curr}_Gmax * ({c2}_Vm - {c1}_Vm);\n"
        )
        if token == "GapJunctionRect+":
            self._v2(c2).append(
                f"\tif({c1}_{c2}_Gap_I > 0) {c1}_{c2}_Gap_I = {c1}_{c2}_{curr}_frac * {c1}_{c2}_Gap_I;\n"
            )
        elif token == "GapJunctionRect-":
            self._v2(c2).append(
                f"\tif({c1}_{c2}_Gap_I < 0) {c1}_{c2}_Gap_I = {c1}_{c2}_{curr}_frac * {c1}_{c2}_Gap_I;\n"
            )
        self._v3(c2).append(f"- {c1}_{c2}_Gap_I ")

    def Make_Iext_in_dVm(self):
        # awk computed def_Iext but never wrote/used it elsewhere; kept for parity (no-op).
        pass

    def Make_dCa(self):
        cell = self.cell
        name = f"{cell}_Ca"
        self.dmh[self.num_odes - 1] = (
            f"\t return ( ({name}inf({cell}_Vm, {cell}_ICa) - {name}) / "
            f"{name}tau({cell}_Vm, {cell}_ICa) );"
        )

    def Make_dmh(self, mh):
        cell, curr = self.cell, self.curr
        if self.cadep:
            varin = f"{cell}_Vm, {cell}_Ca"
            self.tmpca.append(f"{cell}_{curr}_{mh}inf\n")
            self.tmpca.append(f"{cell}_{curr}_{mh}tau\n")
        else:
            varin = f"{cell}_Vm"
        name = f"{cell}_{curr}_{mh}"
        self.dmh[self.num_odes - 1] = (
            f"\t return ( ({name}inf({varin}) - {name}) / {name}tau({varin}) );"
        )

    def Make_dmh_alphabeta(self, mh):
        cell, curr = self.cell, self.curr
        name = f"{cell}_{curr}_{mh}"
        self.dmh[self.num_odes - 1] = (
            f"\t return ( ({name}alpha({cell}_Vm)*(1 - {name}) - {name}beta({cell}_Vm)*{name}) );"
        )

    def Make_syn_dmh(self, mh):
        curr = self.curr
        name = f"{self.syn}_{curr}_{mh}"
        self.dmh[self.num_odes - 1] = (
            f"\treturn ( ({name}inf({self.cellpre}_Vm) - {name}) / {name}tau({self.cellpre}_Vm) );"
        )

    def Make_synpost_dmh(self, mh):
        curr = self.curr
        name = f"{self.syn}_{curr}_{mh}"
        self.dmh[self.num_odes - 1] = (
            f"\t return ( ({name}inf({self.cell}_Vm) - {name}) / {name}tau({self.cell}_Vm) );"
        )

    def Write_dmh(self, n):
        self.derivs_h.append(f"double RHS{n}(double t, double *Y);\n")
        self.m1.append(f"double RHS{n}(double t, double *Y)\n{{\n")
        self.m1.append(self.dmh[n])
        self.m1.append("\n}\n\n")

    def Write_ode(self, n):
        if self.type[n] != "Vm":
            self.Write_dmh(n)

    def Write_all(self):
        for n in range(self.old_num_odes, self.num_odes):
            self.Write_ode(n)
        self.old_num_odes = self.num_odes

    def Write_cell(self, n, cl):
        ode_n = self.ode[n]
        self.derivs_h.append(f"double RHS{ode_n}(double t, double *Y);\n")
        self.bufV1.append(f"double RHS{ode_n}(double t, double *Y)\n{{\n")
        self.bufV1.extend(self.V1.get(cl, []))
        self.bufV1.append(self.tmpddd.get(cl, "//\n"))
        self.bufV1.extend(self.V4.get(cl, []))
        self.bufV1.extend(self.V2.get(cl, []))
        if not self.FirstCa.get(cl, True):
            self.bufV1.extend(self.V6ca.get(cl, []))
        self.bufV1.append(f"\treturn( (1.0/{cl}_Cm) * ({cl}_Iext ")
        self.bufV1.extend(self.V3.get(cl, []))
        self.bufV1.append(") );\n}\n")

    def Write_node(self, n):
        nd = self.node_name[n]
        self.bufNd1.append("\tp = 0")
        self.bufNd1.extend(self.Nd1.get(nd, []))
        self.bufNd1.append(";\n\tq = 0")
        self.bufNd1.extend(self.Nd2.get(nd, []))
        self.bufNd1.append(f";\n\tif(q>0) {nd}_Vnode = p/q;\n")

    def Write_vclamp(self, n, cl):
        self.tmpprotovc.append(f"double VClampI{n}(double t, double *Y);\n")
        self.bufV1.append(f"double VClampI{n}(double t, double *Y)\n{{\n")
        self.bufV1.extend(self.V1.get(cl, []))
        self.bufV1.extend(self.V4.get(cl, []))
        self.bufV1.extend(self.V2.get(cl, []))
        if not self.FirstCa.get(cl, True):
            self.bufV1.extend(self.V6ca.get(cl, []))
        self.bufV1.append("\treturn( ")
        self.bufV1.extend(self.V3.get(cl, []))
        self.bufV1.append(" );\n}\n")

    # ---- main line-by-line driver (awk `{...}` body) -----------------------
    def process_line(self, fields: list[str]):
        if not fields:
            return
        self.cadep = 0
        token = fields[0]
        self.token = token
        nf = len(fields)

        if token == "global":
            for name in fields[1:]:
                self.add_global2pars(name)
        elif token == "node":
            name = fields[1]
            self.node_name.append(name)
            self.num_nodes += 1
            self.Write_Global_Vnode(name, 0)
        elif token in ("cell", "compartment"):
            cell = fields[1]
            self.cell = cell
            self.FirstCa[cell] = True
            is_vclamp = nf >= 3 and fields[2] in ("vclamp", "voltageclamp")
            if not is_vclamp:
                if not self.First:
                    self.Write_all()
                self.First = False
                self.object = token
                self.cl.append(cell)
                self.ode.append(self.num_odes)
                self.num_cells += 1
                self.Write_vars_in_defs(cell, "Vm")
                self.Write_cell_pars("Cm")
                self.Write_cell_pars("Iext")
                self.Write_cell_pars("Ga")
                self.Make_Iext_in_dVm()
            else:
                if self.FirstVC:
                    self.FirstVC = False
                    self.defs.append("#define VOLTAGE_CLAMP\n")
                self.Write_Global_Vm(cell, 0)
                self.vcl.append(cell)
                self.num_vcs += 1
                if not self.First:
                    self.Write_all()
                self.First = False
                self.object = token
                self.Write_cell_pars("Cm")
                self.Write_cell_pars("Ga")
                self._v1(cell)  # ensure buffer exists (awk: print "" >> fV1 cell)
        elif token == "synapse":
            self.object = token
            self.syn = f"{fields[1]}_{fields[2]}"
            self.cell = fields[2]
            self.cellpre = fields[1]
            self.keep = False
        elif token == "connect":
            self.object = token
            comp1, comp2 = fields[1], fields[2]
            self.Stick_Iaxial_in_dVm(comp1, comp2)
            self.Stick_Iaxial_in_dVm(comp2, comp1)
        elif token == "connect2node":
            self.object = token
            comp, node = fields[1], fields[2]
            self.Stick_node_Iaxial_in_dVm(comp, node)
        elif self.object in ("cell", "compartment"):
            self._process_cell_current(fields)
        elif self.object == "synapse":
            self._process_synapse_current(fields)

    def _process_cell_current(self, fields):
        token = self.token
        cell = self.cell
        curr = fields[1]
        self.curr = curr
        nf = len(fields)
        last = fields[-1]
        if last.lower() == "keep":
            self.keep = True
            self.Write_keep(cell, curr, "G")
            self.Write_keep(cell, curr, "I")
        else:
            self.keep = False

        depcurr = []
        for i in range(nf - 1, 1, -1):
            if "Dep" in fields[i]:
                depcurr.append(fields[i].replace("Dep", "", 1))
        # awk loops i from NF downto 3 (i>2), incrementing cadep as it appends;
        # our loop above iterates the same range/order (nf-1 .. 2, 1-indexed
        # awk fields[i] for i in range(nf-1,1,-1) corresponds to python 0-indexed fields[i]
        # for i in range(nf-1, 1, -1) -> fields index nf-1 down to 2 (i.e. awk $NF down to $3)
        self.cadep = len(depcurr)

        if self.cadep and self.FirstCa.get(cell, True):
            self.FirstCa[cell] = False
            self.Write_vars_in_defs(cell, "Ca")
            self.Make_dCa()
            self.Write_keep(cell, "", "ICa")
            self.Write_I_in_ICa(cell, None, 0)
            self.Write_ca_prototype(cell, "Cainf")
            self.Write_ca_prototype(cell, "Catau")
            for dc in depcurr:
                self.Write_I_in_ICa(cell, dc, 1)

        if token == "Passive":
            self.Write_Gmax_Erev(cell, curr)
            self.Stick_I_in_dVm(cell, curr)
        elif token == "mInst":
            self.Write_Gmax_Erev(cell, curr)
            self.Write_power("m")
            self.Write_prototype(cell, "minf")
            self.Stick_I_in_dVm(cell, curr)
        elif token == "mTauInf":
            self.Write_vars_in_defs(cell, "m")
            self.Write_Gmax_Erev(cell, curr)
            self.Write_power("m")
            self.Write_prototype(cell, "minf")
            self.Write_prototype(cell, "mtau")
            self.Make_dmh("m")
            self.Stick_I_in_dVm(cell, curr)
        elif token == "mInst_hTauInf":
            self.Write_vars_in_defs(cell, "h")
            self.Write_Gmax_Erev(cell, curr)
            self.Write_power("m")
            self.Write_power("h")
            self.Write_prototype(cell, "minf")
            self.Write_prototype(cell, "hinf")
            self.Write_prototype(cell, "htau")
            self.Make_dmh("h")
            self.Stick_I_in_dVm(cell, curr)
        elif token == "mhTauInf":
            self.Write_Gmax_Erev(cell, curr)
            self.Write_vars_in_defs(cell, "m")
            self.Write_power("m")
            self.Make_dmh("m")
            self.Write_prototype(cell, "minf")
            self.Write_prototype(cell, "mtau")
            self.Write_vars_in_defs(cell, "h")
            self.Write_power("h")
            self.Write_prototype(cell, "hinf")
            self.Write_prototype(cell, "htau")
            self.Make_dmh("h")
            self.Stick_I_in_dVm(cell, curr)
        elif token == "mAlphaBeta":
            self.Write_vars_in_defs(cell, "m")
            self.Write_Gmax_Erev(cell, curr)
            self.Write_power("m")
            self.Write_prototype(cell, "malpha")
            self.Write_prototype(cell, "mbeta")
            self.Make_dmh_alphabeta("m")
            self.Stick_I_in_dVm(cell, curr)
        elif token == "mhAlphaBeta":
            self.Write_Gmax_Erev(cell, curr)
            self.Write_vars_in_defs(cell, "m")
            self.Write_power("m")
            self.Make_dmh_alphabeta("m")
            self.Write_prototype(cell, "malpha")
            self.Write_prototype(cell, "mbeta")
            self.Write_vars_in_defs(cell, "h")
            self.Write_power("h")
            self.Write_prototype(cell, "halpha")
            self.Write_prototype(cell, "hbeta")
            self.Make_dmh_alphabeta("h")
            self.Stick_I_in_dVm(cell, curr)

    def _process_synapse_current(self, fields):
        self.Depress = False
        token = self.token
        curr = fields[1]
        self.curr = curr
        property_ = fields[2] if len(fields) > 2 else ""
        syn, cell = self.syn, self.cell
        last = fields[-1]
        if last.lower() == "keep":
            self.keep = True
            self.Write_keep(syn, curr, "G")
            self.Write_keep(syn, curr, "I")
        else:
            self.keep = False

        if token == "GradedmInst":
            self.Write_Gmax_Erev(syn, curr)
            self.Write_prototype(syn, "minf")
            self.Stick_I_in_dVm(syn, curr)
        elif token == "GradedmTauInf":
            self.Write_vars_in_defs(syn, "m")
            self.Write_Gmax_Erev(syn, curr)
            self.Write_prototype(syn, "minf")
            self.Write_prototype(syn, "mtau")
            self.Make_syn_dmh("m")
            self.Stick_I_in_dVm(syn, curr)
        elif token == "GradedmhTauInf":
            if property_.lower() == "depressing":
                self.Depress = True
            self.Write_vars_in_defs(syn, "m")
            self.Write_Gmax_Erev(syn, curr)
            self.Write_prototype(syn, "minf")
            self.Write_prototype(syn, "mtau")
            self.Make_syn_dmh("m")
            self.Write_vars_in_defs(syn, "h")
            self.Write_prototype(syn, "hinf")
            self.Write_prototype(syn, "htau")
            self.Make_syn_dmh("h")
            self.Stick_I_in_dVm(syn, curr)
        elif token == "GradedmInst_mpostInst":
            self.Write_Gmax_Erev(syn, curr)
            self.Write_prototype(syn, "minf")
            self.Write_prototype(syn, "mpostinf")
            self.Stick_I_in_dVm(syn, curr)
        elif token == "GradedmTauInf_mpostTauInf":
            self.Write_vars_in_defs(syn, "m")
            self.Write_Gmax_Erev(syn, curr)
            self.Write_prototype(syn, "minf")
            self.Write_prototype(syn, "mtau")
            self.Make_syn_dmh("m")
            self.Write_vars_in_defs(syn, "mpost")
            self.Write_prototype(syn, "mpostinf")
            self.Write_prototype(syn, "mposttau")
            self.Make_synpost_dmh("mpost")
            self.Stick_I_in_dVm(syn, curr)
        elif "GapJunction" in token:
            self.Write_Ggap(syn)
            self.Stick_Igap_in_dVm(self.cellpre, cell, token)
        elif token == "AlphaFunction":
            self.Write_Gmax_Erev(syn, curr)
            self.Write_Global("AlphaTau", "10", syn, curr)
            if self.cellpre == "NULL":
                self.Write_Global("Period", "100", syn, curr)
            else:
                self.Write_Global("Threshold", "0", syn, curr)
                self.Write_Global("Slope", "1", syn, curr)
            self.Write_Global("Tolerance", "1e-3", syn, curr)
            self.Stick_I_in_dVm(syn, curr)
        elif token == "PulseStim":
            if self.cellpre == "NULL":
                self.Write_Global("Period", 0, syn, curr)
                self.Write_Global("Duration", 0, syn, curr)
                self.Write_Global("Amplitude", 0, syn, curr)
                self.Stick_Ipulse_in_dVm(syn, curr)
        elif token == "ControlledPulse":
            self.Write_Global("Period", 0, syn, curr)
            self.Write_Global("Duration", 0, syn, curr)
            self.Write_Global("Amplitude", 0, syn, curr)
            self.Write_Global("Threshold", 0, syn, curr)
            self.Write_Global("Delay", 0, syn, curr)
            self.Write_Global("Above", TRUE, syn, curr)
            self.Stick_IControlled_in_dVm(syn, curr)

    # ---- END block ----------------------------------------------------------
    def finalize(self):
        for i in range(self.num_cells):
            self.Write_cell(i, self.cl[i])
        if self.num_nodes > 0:
            self.bufNd1.insert(0, "void update_nodes(double t, double *Y)\n{\ndouble p, q;\n")
            for i in range(self.num_nodes):
                self.Write_node(i)
            self.bufNd1.append("\n}\n")
            self.defs.append("#define NODES\n")
        for i in range(self.num_vcs):
            self.Write_vclamp(i, self.vcl[i])
        self.Write_all()

        self.defs.append(f"#define NUMODES {self.num_odes}\n")
        if self.num_vcs > 0:
            self.defs.append(f"#define NUMVCS {self.num_vcs}\n")
        keep_init = None
        if self.num_keep > 0:
            self.defs.append(f"#define NUMKEEPS {self.num_keep}\n")
            parts = []
            for i in range(self.num_keep - 1):
                parts.append("0.0, ")
                if i % 8 == 2:
                    parts.append("\n")
            parts.append("0.0")
            keep_init = f"double G[NUMKEEPS]={{{''.join(parts)}}};\n"
        self.tmpg1 = keep_init or ""
        return self.num_odes


def parse_cfg_text(cfg_text: str) -> tuple[CfgCompiler, int]:
    """Strip # comments (awk split on '#', field 1) and feed each non-empty
    line to a fresh CfgCompiler. Returns (compiler, num_odes)."""
    comp = CfgCompiler()
    for raw in cfg_text.splitlines():
        code = raw.split("#", 1)[0]
        fields = code.split()
        if fields:
            comp.process_line(fields)
    n = comp.finalize()
    return comp, n
