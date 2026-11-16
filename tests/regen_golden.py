#!/usr/bin/env python3
"""Run the ORIGINAL network_2_11 toolchain on every regression case.

    python3 tests/regen_golden.py /path/to/network_2_11            # rewrite golden/*.out
    python3 tests/regen_golden.py /path/to/network_2_11 --compare  # also run netgen, require identical output

Needs bash, gawk, gcc and make. The original `network` script hardcodes
NETWORKHOME=$HOME/bin/network_2_11, so this runs it with HOME pointed at a
temporary directory that links bin/network_2_11 to the path you give.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cases import CASES, GOLDEN_DIR, PROJECTS_DIR  # noqa: E402

REPO = Path(__file__).resolve().parent.parent


def _setup(case, dest: Path) -> None:
    shutil.copytree(PROJECTS_DIR / case.project_dir, dest)
    if case.empty_var:
        (dest / f"{case.project}.var").write_text("")


def run_original(case, network_home: Path, work: Path) -> bytes:
    fake_home = work / "home"
    (fake_home / "bin").mkdir(parents=True, exist_ok=True)
    link = fake_home / "bin" / "network_2_11"
    if not link.exists():
        link.symlink_to(network_home.resolve())
    d = work / "orig" / case.name
    _setup(case, d)
    env = dict(os.environ, HOME=str(fake_home))
    cmd = ["bash", str(link / "network"), *case.flags, case.project]
    r = subprocess.run(cmd, cwd=d, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return r.stdout


def run_netgen(case, work: Path) -> bytes:
    d = work / "py" / case.name
    _setup(case, d)
    env = dict(os.environ, PYTHONPATH=str(REPO))
    cmd = [sys.executable, "-m", "netgen", *case.flags, case.project]
    r = subprocess.run(cmd, cwd=d, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return r.stdout


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("network_home", type=Path, help="directory holding the original network, parse_network, ...")
    ap.add_argument("--compare", action="store_true", help="also run netgen and require byte-identical output")
    args = ap.parse_args()

    GOLDEN_DIR.mkdir(exist_ok=True)
    fail = 0
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        for case in CASES:
            orig = run_original(case, args.network_home, work)
            if not orig:
                print(f"FAIL  {case.name}: original produced no output")
                fail = 1
                continue
            (GOLDEN_DIR / f"{case.name}.out").write_bytes(orig)
            nlines = orig.count(b"\n")
            line = f"{case.name}: {nlines} lines"
            if args.compare:
                same = run_netgen(case, work) == orig
                fail |= not same
                line = ("PASS  " if same else "FAIL  ") + line
            print(line)
    return fail


if __name__ == "__main__":
    sys.exit(main())
