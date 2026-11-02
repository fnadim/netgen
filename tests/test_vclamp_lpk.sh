#!/bin/bash
# Regression test: voltage-clamped LPK project, Python port vs original `network`.
# Runs each case with and without an empty LPK.var and requires identical output.
# Needs the original toolchain (`network`) on PATH. Usage: tests/test_vclamp_lpk.sh
set -e
here="$(cd "$(dirname "$0")" && pwd)"
pkg="$(dirname "$here")"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
fail=0
for var in none empty; do
    for d in orig py; do
        mkdir -p "$work/$var/$d"
        cp "$here"/vclamp_lpk/LPK.* "$work/$var/$d"/
        [ $var = empty ] && : > "$work/$var/$d/LPK.var"
    done
    (cd "$work/$var/orig" && script -qec 'network LPK > out' /dev/null > /dev/null)
    (cd "$work/$var/py" && PYTHONPATH="$pkg" python3 -m netgen LPK > out 2> /dev/null)
    if cmp -s "$work/$var/orig/out" "$work/$var/py/out"; then
        echo "PASS  .var=$var  ($(wc -l < "$work/$var/py/out") lines, $(head -1 "$work/$var/py/out" | wc -w) columns)"
    else
        echo "FAIL  .var=$var"; fail=1
    fi
done
exit $fail
