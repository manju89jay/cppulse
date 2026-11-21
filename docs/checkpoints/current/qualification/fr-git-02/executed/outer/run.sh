#!/usr/bin/env bash
set -euo pipefail
work=/workspace/work
base="$work/current38-batch11"
out="$base/results"
inventory="$work/current38-next/criteria/runtime_inventory.py"
mkdir "$out"
python3 -B "$inventory" check "$out/runtime-before.json"
overall=0
record() {
    local label=$1
    shift
    local run=0
    "$@" > "$out/$label.stdout" 2>&1 || run=$?
    printf '%d\n' "$run" > "$out/$label.exit"
    printf '%s phase exit %d\n' "$label" "$run"
    tail -12 "$out/$label.stdout"
    if (( run != 0 )); then overall=$run; fi
}
record history-streaming bash "$base/history-streaming/launch.sh" "$out/history-streaming"
record generated-wiring bash "$work/current38-m1-review/run.sh"
python3 -B "$inventory" check "$out/runtime-after.json"
cmp "$out/runtime-before.json" "$out/runtime-after.json"
exit "$overall"
