"""Regression cases shared by test_regression.py and regen_golden.py.

Each case runs one project from tests/projects/<dir>/ with the given flags.
Its expected output, tests/golden/<case>.out, was produced by the ORIGINAL
network_2_11 toolchain (see regen_golden.py), so these tests check that
netgen stays output-compatible with the original.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
PROJECTS_DIR = TESTS_DIR / "projects"
GOLDEN_DIR = TESTS_DIR / "golden"


@dataclass(frozen=True)
class Case:
    name: str              # golden file is golden/<name>.out
    project_dir: str       # directory under tests/projects/
    project: str           # project basename (projectname.cfg, ...)
    flags: tuple = ()      # extra command-line flags, same for both tools
    empty_var: bool = False  # create an empty projectname.var before running
    covers: str = field(default="", compare=False)


CASES = [
    Case("hh", "hh", "hh", covers="mhAlphaBeta/mAlphaBeta gating"),
    Case("hh_tabulate", "hh", "hh", ("-t",), covers="-t (tabulate) flag"),
    Case("hh_flags", "hh", "hh", ("-b", "10", "-e", "30", "-h", "0.01", "-s", "5", "-tol", "1e-6"),
         covers="-b -e -h -s -tol flags"),
    Case("hhvc", "hhvc", "hhvc", covers="vclamp cell, no .opt file"),
    Case("passive", "passive", "passive", covers="single passive cell"),
    Case("depressing_synapse", "depressing_synapse", "syn",
         covers="Depressing graded synapse, varfileoption in .opt"),
    Case("nodes", "node", "node", covers="node / connect2node"),
    Case("alpha_function_null", "alpha_function", "a",
         covers="AlphaFunction synapse from NULL"),
    Case("alpha_function_cell", "alpha_function", "b",
         covers="AlphaFunction synapse between cells, mInst_hTauInf"),
    Case("pulsestim_mcn1", "pulsestim_mcn1", "all",
         covers="PulseStim, ControlledPulse, axial connect"),
    Case("vclamp_lpk", "vclamp_lpk", "LPK",
         covers="vclamp with Verbatim step"),
    Case("vclamp_lpk_empty_var", "vclamp_lpk", "LPK", empty_var=True,
         covers="empty .var with vclamp keeps t, V and I"),
]
