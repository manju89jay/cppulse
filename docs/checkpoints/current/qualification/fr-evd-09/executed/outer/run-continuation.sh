#!/usr/bin/env bash
set -euo pipefail
base=/workspace/work/current38-batch12
out="$base/continuation-runtime"
inventory=/workspace/work/current38-next/criteria/runtime_inventory.py
mkdir "$out"
python3 -B "$inventory" check "$out/runtime-before.json"
actual=0
bash "$base/coverage-continuation/launch.sh" "$base/continuation-results" \
    > "$out/actual.log" 2>&1 || actual=$?
printf '%d\n' "$actual" > "$out/actual.exit"
tail -22 "$out/actual.log"
python3 -B "$inventory" check "$out/runtime-after.json"
cmp "$out/runtime-before.json" "$out/runtime-after.json"
exit "$actual"
