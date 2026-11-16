# netgen regression tests

`pytest tests` runs netgen on every case in `cases.py` and compares the
output with `golden/<case>.out`. Those golden files were produced by the
**original** `network_2_11` toolchain, so a passing run means netgen still
gives the same results as the original. Headers must match exactly;
numbers are compared to 1e-6 so a different compiler or CPU does not
cause false failures (on the machine that generated them the outputs are
byte-identical). Needs `gcc` and `make`.

## Projects

| Directory | Exercises |
|---|---|
| `hh` | Hodgkin-Huxley cell with `mhAlphaBeta`/`mAlphaBeta`; also `-t` and the `-b -e -h -s -tol` flags |
| `hhvc` | `vclamp` cell, no `.opt` file |
| `passive` | single passive cell |
| `depressing_synapse` | `Depressing` graded synapse; `varfileoption` set in `.opt` |
| `node` | `node` / `connect2node` |
| `alpha_function` | `AlphaFunction` synapses, from `NULL` (`a`) and from a cell (`b`) |
| `pulsestim_mcn1` | `PulseStim`, `ControlledPulse`, axial `connect` |
| `vclamp_lpk` | `vclamp` with a `Verbatim` step, with and without an empty `.var` |

Run lengths in some `.opt` files were shortened to keep the golden files
small. The `node` project's `Verbatim` printed `ABC_Vm`, which doesn't
exist (it fails in the original too), so it prints `ABC_Vnode` instead.

Note that, as in the original, values in `projectname.opt` override the
`-e`/`-h`/`-s`/... command-line flags.

## Regenerating the golden files

Only needed when you add a case or intentionally change the output.
With the original toolchain available (bash, gawk, gcc, make):

```
python3 tests/regen_golden.py /path/to/network_2_11 --compare
```

This rewrites `golden/*.out` from the original and, with `--compare`,
also checks that netgen's output is byte-identical.
