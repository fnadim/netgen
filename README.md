# netgen (Python port of network_2_11)

A Python replacement for the `network` / `parse_network` / `tabulate_network`
bash+gawk toolchain (v2.11). This ports the **orchestration and
code-generation** layer to Python; the numerical integration engine itself
(`runcell.c`, `numtools.c`/`.h`) is bundled **unchanged** from the original
C sources and is still compiled with `gcc` and run as a native binary. A
`.cfg`/`.par` project that worked with the original toolchain works with
this one too, unmodified.

Validated against the original toolchain on real projects from
`ABPDPD_2026` and `tmp`:

* `ab` (single compartment, no synapses) — output matches the original
  byte-for-byte.
* `abpdpd` (3 cells / 5 compartments, gap junctions + axial coupling +
  a stochastic `Verbatim` current) — output matches the original
  byte-for-byte over a 5000 ms run (re-checked 2026-11-16).
* `hh` (classic Hodgkin-Huxley cell using `mhAlphaBeta`/`mAlphaBeta`
  alpha/beta-style gating, rather than `mTauInf`/`mhTauInf`) — output
  matches the original byte-for-byte (now a regression test).
* `abpd` (2 cells / 4 compartments, `keep`-exposed currents, a
  `CaXDep`-modifier calcium-concentration-dependent current (`KCa`), the
  auto-generated per-cell calcium-pool ODE (`Cainf`/`Catau`), a
  `Verbatim` block with local variable declarations, and custom-named
  (non-`E`) `GapJunction` synapses) — output matches the original
  byte-for-byte over a full 10000 ms / 200000-step run, on both the
  full state vector and the project's own 2-column restricted `.var`
  output.

  This test caught and fixed a real bug: `make_inf_tau_file`'s handling
  of Ca-dependent `inf`/`tau` functions was collapsed into a single
  (wrong) check, instead of the original's two separate passes — one
  that special-cases `Cainf`/`Catau` function names (giving them a
  second `double ica` parameter), and a second, independent pass that
  widens any function whose name was flagged Ca-dependent during `.cfg`
  parsing (e.g. a `KCa` current with a `CaXDep` modifier) to take a
  second `double ca` parameter. The port now runs both passes
  separately, matching the original exactly (see `pars.py`).

(Note: an early round of this validation looked like it had turned up a
real numerical bug — the original toolchain's generated `derivs.c` had
every cell's code duplicated 2-3x. That turned out to be an artifact of
this sandboxed environment repeatedly re-running the original scripts
against the same scratch directory without being able to `rm` the
gawk-generated temp files between runs (`parse_network`'s temp files are
built with `>>` append, assuming a clean directory each time). A
genuinely fresh run of the original toolchain produces clean, correctly
generated code, which is what's being compared above.)

## Install / requirements

Python 3.9+, `gcc`, and `make` on PATH. No third-party Python packages
required.

Install it once (from a clone of this repository) to get a `netgen`
command:

```
pip install .                                      # or: pip install -e .  to edit in place
pip install git+https://github.com/fnadim/netgen   # straight from GitHub
```

Without installing, `python3 -m netgen` still works from the repository
directory (or with it on `PYTHONPATH`).

## Usage

```
netgen [OPTIONS] projectname
```

Run from the project directory (the one containing `projectname.cfg`,
`projectname.par`, etc.), same as the original `network` command.

### Flag mapping from the original `network`

| Original       | Python port     | Meaning                                   |
|-----------------|-----------------|--------------------------------------------|
| `-rm`           | `-rm`           | remove intermediate files after compiling  |
| `-c`            | `-c`            | parse + compile only, don't run            |
| `-clean`        | `-clean`        | remove NETWORK dir, runnetwork, .networkpars, .networkvars, last |
| `-r`            | `-r`            | skip parse+compile, just refresh `.networkpars` and run (fast path after a `.par` edit) |
| `-ro`           | `-ro`           | run only, using whatever `runnetwork` already exists |
| `-parse`        | `-parse`        | parse (generate C) only, no compile/run    |
| `-tabulate`/`-t`| `-tabulate`/`-t`| build lookup-table optimized `inf_tau.c`   |
| `-tperturb`     | `-tperturb`     | same, with a small table-offset perturbation (for finite-difference sensitivity work) |
| `-notabulate`/`-nt` | `-notabulate`/`-nt` | disable tabulation                    |
| `-par FILE`     | `-par FILE`     | extra `.par` file, concatenated after `projectname.par` |
| `-tol X`        | `-tol X`        | integrator error tolerance (adaptive step) |
| `-b X`          | `-b X`          | start time                                 |
| `-e X`          | `-e X`          | end time                                   |
| `-h X`          | `-h X`          | step size (dt)                             |
| `-s N`          | `-s N`          | output every N steps                       |
| `-k FILE` / `-keep FILE` | `-k FILE` / `-keep FILE` | var-keep file |
| `-v`            | `-v`            | print version and exit                     |

`projectname.opt` (sourced by the original as `KEY=VALUE` shell
assignments) and `projectname.var` are read the same way as before; a
`.opt` file with lines like `dt=0.1` / `tmax=5000` works unchanged.

Output is written to **stdout**, same as the original — redirect it
yourself:

```
netgen abpdpd > oabpdpd
```

### What's different from the original CLI

* This is a real `argv`-parsing Python program, not a shell script —
  invoke it as `netgen` (after `pip install`) or `python3 -m netgen`, not
  bare `network`, unless you set up your own wrapper or symlink.
* No `dd bs=10000` buffering trick on output (that was working around a
  historical shell/pipe issue; Python's stdout buffering handles this
  fine on its own).
* Otherwise the flags, `.opt`/`.var` file handling, and output format are
  designed to be call-compatible with the original — a script like
  `do_abpdpd.sh` needs only `network` renamed to `netgen` (and
  the `NETWORKHOME`/PATH setup removed, since there's no separate compiled
  binary to locate — everything lives in this one Python package plus your
  system's `gcc`/`make`).

## Package layout

```
netgen/
    __init__.py       version string
    __main__.py        entry point (python3 -m netgen)
    cli.py             argv parsing + orchestration (port of `network`)
    codegen.py          .cfg -> C code generation (port of parse_network's cfg-walking logic)
    pars.py             .par handling: comment stripping, get_pars, inf_tau.c generation
    link.py             assembles the final generated files (defs.h, globalvars.h,
                        derivs.h, prototypes.h, init.h, derivs.c, inf_tau.c)
    tabulate.py          lookup-table optimization (port of tabulate_network)
    runtime/            unchanged C sources: runcell.c, numtools.c, numtools.h, makefile
```

## Tests

```
pip install pytest
pytest tests
```

Runs netgen on a set of small projects and compares the output with what
the original `network_2_11` toolchain produced for the same projects.
Between them they cover `node`/`connect2node`, `AlphaFunction`,
`PulseStim`, `ControlledPulse`, `Depressing` synapses, `vclamp`,
alpha/beta and tau/inf gating, and the `-t`, `-b`, `-e`, `-h`, `-s` and
`-tol` flags. GitHub Actions runs them on every push and pull request.
See [tests/README.md](tests/README.md), including how to regenerate the
expected outputs from the original toolchain.

## Known limitations and behaviour inherited from the original

* `-t`/`-tabulate` does **not** change the simulation. The original
  `network` script runs `tabulate_network` on a copy of `inf_tau.c`,
  keeps only the generated `inf_tau_tables.h`, and deletes the rewritten
  `inf_tau.c`, so the model is always compiled with the untabulated
  functions. netgen does the same so that results stay identical.
* Values in `projectname.opt` override the `-b`/`-e`/`-h`/`-s`/`-tol`
  command-line flags, because the original reads the `.opt` file after
  parsing the flags.
* The generated C code calls `inf`/`tau` functions in the order they
  appear in the `.par` file without prototypes. With recent gcc versions
  (14+) that is a compile error when a function is used before the `.par`
  line that defines it, so put shared function definitions (e.g. a
  `shared.par`) before the parameters that use them. The original
  toolchain behaves the same way.
* Validated end-to-end against the original on `ab`, `abpd`, `abpdpd`
  (byte-identical, including `-t`) and on the test projects above. Other
  `parse_network` features that none of these use have been ported
  function-for-function but not run against a real project.
