"""Run netgen on each case in cases.py and compare with the output the
original network_2_11 toolchain produced (tests/golden/).

The header line must match exactly. Numbers are compared with a small
tolerance so that a different compiler or CPU (which can change the last
printed digit) does not fail the test; on the machine that generated the
golden files the output is byte-identical.
"""
from __future__ import annotations

import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from cases import CASES, GOLDEN_DIR, PROJECTS_DIR

REPO = Path(__file__).resolve().parent.parent
REL_TOL = 1e-6
ABS_TOL = 1e-6

pytestmark = pytest.mark.skipif(
    shutil.which("gcc") is None or shutil.which("make") is None,
    reason="netgen needs gcc and make to build the model",
)


def run_netgen(case, tmp_path: Path) -> str:
    d = tmp_path / case.project_dir
    shutil.copytree(PROJECTS_DIR / case.project_dir, d)
    if case.empty_var:
        (d / f"{case.project}.var").write_text("")
    env = dict(os.environ, PYTHONPATH=str(REPO) + os.pathsep + os.environ.get("PYTHONPATH", ""))
    r = subprocess.run(
        [sys.executable, "-m", "netgen", *case.flags, case.project],
        cwd=d, env=env, capture_output=True, text=True,
    )
    assert r.returncode == 0, f"netgen failed:\n{r.stderr[-3000:]}"
    return r.stdout


def assert_same_output(got: str, expected: str) -> None:
    g, e = got.splitlines(), expected.splitlines()
    assert len(g) == len(e), f"line count {len(g)} != expected {len(e)}"
    assert g[0].split() == e[0].split(), f"header {g[0]!r} != expected {e[0]!r}"
    for n, (gl, el) in enumerate(zip(g[1:], e[1:]), start=2):
        gv, ev = gl.split(), el.split()
        assert len(gv) == len(ev), f"line {n}: {len(gv)} columns, expected {len(ev)}"
        for col, (a, b) in enumerate(zip(gv, ev), start=1):
            if a == b:
                continue
            assert math.isclose(float(a), float(b), rel_tol=REL_TOL, abs_tol=ABS_TOL), (
                f"line {n}, column {col}: {a} != expected {b}"
            )


@pytest.mark.parametrize("case", CASES, ids=[c.name for c in CASES])
def test_matches_original(case, tmp_path):
    expected = (GOLDEN_DIR / f"{case.name}.out").read_text()
    assert_same_output(run_netgen(case, tmp_path), expected)
