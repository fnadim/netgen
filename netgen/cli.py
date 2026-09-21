"""
Python port of the `network` bash orchestrator. Interface is intentionally
similar to the original (same short flags) but implemented as a proper
argv-parsing Python CLI rather than a bash getopts loop.

Usage: python3 -m netgen [OPTIONS] projectname
See README.md in this package for the flag mapping from the original tool.
"""
from __future__ import annotations
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import link, pars

PKG_DIR = Path(__file__).resolve().parent
RUNTIME_DIR = PKG_DIR / "runtime"  # bundled runcell.c/numtools.c/numtools.h/makefile


def _read_opt_file(path: Path) -> dict:
    """Minimal `source basename.opt` replacement: parses simple KEY=VALUE
    (or KEY="VALUE") assignment lines. Lines that aren't simple assignments
    are ignored with a warning -- .opt files in practice are just a
    handful of `dt=0.1`-style lines (see README)."""
    opts = {}
    if not path.exists():
        return opts
    for raw in path.read_text().splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if not key.isidentifier():
            print(f"   (opt file) skipping unrecognized line: {raw}", file=sys.stderr)
            continue
        opts[key] = val
    return opts


def _read_var_file(path: Path) -> list[str]:
    names = []
    if not path.exists():
        return names
    for raw in path.read_text().splitlines():
        code = raw.split("#", 1)[0]
        names.extend(code.split())
    return names


class Options:
    def __init__(self):
        self.parse = True
        self.compile = True
        self.run = True
        self.runonly = False
        self.tabulate = False
        self.perturb = 0.0
        self.removefiles = False
        self.tolerance = -1.0
        self.t0 = 0.0
        self.tmax = 100.0
        self.dt = 0.1
        self.skip = 10
        self.par2 = ""
        self.varfileoption = ""
        self.networkdir_name = "NETWORK"


FLAGS_TAKING_ARG = {"-par", "-tol", "-b", "-e", "-h", "-s", "-k", "-keep"}
FLAGS_NO_ARG = {
    "-rm", "-c", "-r", "-ro", "-parse", "-tabulate", "-t", "-tperturb",
    "-nt", "-notabulate", "-clean", "-v",
}


def parse_argv(argv: list[str]) -> tuple[Options, str]:
    o = Options()
    i = 0
    while i < len(argv) and argv[i] in FLAGS_TAKING_ARG | FLAGS_NO_ARG:
        flag = argv[i]
        if flag == "-rm":
            o.removefiles = True; i += 1
        elif flag == "-c":
            o.run = False; o.compile = True; i += 1
        elif flag == "-clean":
            o.run = o.compile = o.parse = o.tabulate = False
            o.removefiles = False
            i += 1
            return o, "__CLEAN__"
        elif flag == "-r":
            o.compile = False; o.run = True; i += 1
        elif flag == "-ro":
            o.parse = o.compile = o.run = False; o.runonly = True; i += 1
        elif flag == "-parse":
            o.compile = False; o.run = False; i += 1
        elif flag in ("-tabulate", "-t"):
            o.tabulate = True; i += 1
        elif flag == "-tperturb":
            o.tabulate = True; o.perturb = 1e-4; i += 1
        elif flag in ("-notabulate", "-nt"):
            o.tabulate = False; i += 1
        elif flag == "-par":
            o.par2 = argv[i + 1]; i += 2
        elif flag == "-tol":
            o.tolerance = float(argv[i + 1]); i += 2
        elif flag == "-b":
            o.t0 = float(argv[i + 1]); i += 2
        elif flag == "-e":
            o.tmax = float(argv[i + 1]); i += 2
        elif flag == "-h":
            o.dt = float(argv[i + 1]); i += 2
        elif flag == "-s":
            o.skip = int(argv[i + 1]); i += 2
        elif flag in ("-k", "-keep"):
            o.varfileoption = argv[i + 1]; i += 2
        elif flag == "-v":
            print("network (Python port) version 2.11-py")
            sys.exit(0)
        else:
            i += 1
    if i >= len(argv):
        print("Usage: network [OPTIONS] projectname", file=sys.stderr)
        sys.exit(1)
    basename = argv[i]
    return o, basename


def clean(project_dir: Path, o: Options):
    shutil.rmtree(project_dir / o.networkdir_name, ignore_errors=True)
    for f in ("runnetwork", ".networkpars", ".networkvars", "last"):
        (project_dir / f).unlink(missing_ok=True)


def parsecmd(project_dir: Path, basename: str, merged_par_text: str, o: Options) -> dict:
    build_dir = project_dir / o.networkdir_name
    build_dir.mkdir(exist_ok=True)
    print("   Parsing Expressions...", file=sys.stderr)

    cfg_text = (project_dir / f"{basename}.cfg").read_text()
    files = link.generate(cfg_text, merged_par_text)

    for name in ("defs.h", "globalvars.h", "derivs.h", "prototypes.h",
                 "init.h", "derivs.c", "inf_tau.c"):
        (build_dir / name).write_text(files[name])
    (project_dir / ".networkpars").write_text(files[".networkpars"])

    for rt_file in ("runcell.c", "numtools.c", "numtools.h"):
        shutil.copy(RUNTIME_DIR / rt_file, build_dir / rt_file)
    shutil.copy(RUNTIME_DIR / "makefile", build_dir / "Makefile")
    return files


def tabulatecmd(project_dir: Path, o: Options):
    from . import tabulate as tab_mod
    build_dir = project_dir / o.networkdir_name
    inf_tau_c = (build_dir / "inf_tau.c").read_text()
    new_c, tables_h = tab_mod.tabulate(inf_tau_c, perturb=o.perturb)
    (build_dir / "inf_tau.c").write_text(new_c)
    (build_dir / "inf_tau_tables.h").write_text(tables_h)


def compilecmd(project_dir: Path, o: Options):
    print("   Compiling C files...", file=sys.stderr)
    build_dir = project_dir / o.networkdir_name
    result = subprocess.run(["make"], cwd=build_dir, capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write(result.stdout)
        sys.stderr.write(result.stderr)
        raise RuntimeError(f"compile failed (see stderr) in {build_dir}")
    subprocess.run(["make", "clean"], cwd=build_dir, capture_output=True, text=True)
    shutil.move(str(build_dir / "runcell"), str(project_dir / "runnetwork"))


def removefiles(project_dir: Path, o: Options):
    shutil.rmtree(project_dir / o.networkdir_name, ignore_errors=True)


def _run_binary(project_dir: Path, basename: str, o: Options):
    ics = project_dir / f"{basename}.ics"
    args = [
        str(project_dir / "runnetwork"),
        f"-b{o.t0}", f"-e{o.tmax}", f"-h{o.dt}", f"-s{o.skip}",
        f"-t{o.tolerance}", f"-k{o.varfileoption}",
    ]
    if ics.exists():
        args.append(str(ics))
        print(f"   running with {basename}.ics", file=sys.stderr)
    else:
        print("   running without ics", file=sys.stderr)

    # No implicit output-file handling: like most Unix tools, this writes
    # to stdout and the caller redirects (`python3 -m netgen project >
    # oabpdpd`), matching how the original's do_*.sh scripts already
    # invoke `network` today.
    subprocess.run(args, cwd=project_dir, check=True)
    print("   done", file=sys.stderr)


def runcmd(project_dir: Path, basename: str, merged_par_text: str, o: Options):
    # Original always re-runs the -r (get_pars-only) pass right before
    # executing, so a fresh .networkpars matches the latest .par text even
    # if it changed since parsecmd (-par extra file, etc.).
    networkpars = link.rerun_pars(merged_par_text)
    (project_dir / ".networkpars").write_text(networkpars)
    _run_binary(project_dir, basename, o)


def main(argv: list[str] | None = None):
    argv = list(sys.argv[1:] if argv is None else argv)
    o, basename_or_clean = parse_argv(argv)
    project_dir = Path.cwd()

    if basename_or_clean == "__CLEAN__":
        # original's -clean reads no basename at all; nothing further to do
        # (it needs a networkdir name, which defaults to "NETWORK")
        clean(project_dir, o)
        return
    basename = basename_or_clean

    opt_file = project_dir / f"{basename}.opt"
    for k, v in _read_opt_file(opt_file).items():
        if hasattr(o, k):
            cur = getattr(o, k)
            caster = type(cur) if not isinstance(cur, bool) else (lambda x: x not in ("0", "false", "False"))
            try:
                setattr(o, k, caster(v))
            except (TypeError, ValueError):
                setattr(o, k, v)

    var_names = _read_var_file(project_dir / f"{basename}.var")
    if var_names:
        (project_dir / ".networkvars").write_text("\n".join(var_names) + "\n")
        o.varfileoption = ".networkvars"

    par_parts = [(project_dir / f"{basename}.par").read_text()]
    if o.par2:
        par_parts.append(Path(o.par2).read_text())
    merged_par_text = "\n".join(par_parts)

    if o.parse:
        parsecmd(project_dir, basename, merged_par_text, o)
    if o.tabulate:
        tabulatecmd(project_dir, o)
    if o.compile:
        compilecmd(project_dir, o)
    if o.removefiles:
        removefiles(project_dir, o)
    if o.run:
        runcmd(project_dir, basename, merged_par_text, o)
    if o.runonly:
        _run_binary(project_dir, basename, o)


if __name__ == "__main__":
    main()
