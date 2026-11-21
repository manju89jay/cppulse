#!/usr/bin/env bash
set -euo pipefail
base=/workspace/work/current38-batch12
out="$base/results"
inventory=/workspace/work/current38-next/criteria/runtime_inventory.py
mkdir "$out"
python3 -B "$inventory" check "$out/runtime-before.json"
run=0
bash "$base/coverage-dimensions/launch.sh" "$out/coverage-dimensions" > "$out/coverage-dimensions.stdout" 2>&1 || run=$?
printf '%d\n' "$run" > "$out/coverage-dimensions.exit"
tail -14 "$out/coverage-dimensions.stdout"
python3 -B "$inventory" check "$out/runtime-after.json"
cmp "$out/runtime-before.json" "$out/runtime-after.json"
exit "$run"
