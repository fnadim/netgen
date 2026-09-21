"""netgen: a Python port of network_2_11 (network/parse_network/tabulate_network).

See README.md for usage. The numerical integration engine (runcell.c,
numtools.c/.h) is unchanged from the original C sources -- only the
shell/awk orchestration and code-generation layer has been ported to
Python. Generated cell/synapse C code is still compiled with gcc and run
as a native binary.
"""
__version__ = "2.11-py.1"
