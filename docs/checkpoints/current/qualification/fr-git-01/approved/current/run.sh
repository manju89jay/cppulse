#!/usr/bin/env bash
set -euo pipefail

base=/workspace/work/git-scope-qualification/gates
inventory=/workspace/work/current38-next/criteria/runtime_inventory.py
phase=$1
freeze=$2
out=$(realpath -m "$3")
[[ "$out" == "$base/"* ]]
mkdir "$out"
python -B "$inventory" check "$out/runtime-before.json"
overall=0

run_phase() {
    local name=$1
    local where=$2
    local status=0
    bash "$base/container.sh" "$name" "$freeze" "$where" > "$out/$name.stdout" 2>&1 || status=$?
    printf '%d\n' "$status" > "$out/$name.exit"
    printf '%s exit %d\n' "$name" "$status"
    tail -12 "$out/$name.stdout"
    if [[ "$status" -ne 0 ]]; then overall=$status; fi
}

case "$phase" in
    package) run_phase package "$out" ;;
    tests)
        for group in git-public git-source git-installed; do
            mkdir "$out/$group"
            run_phase "$group" "$out/$group"
        done ;;
    *) exit 2 ;;
esac
python -B "$inventory" check "$out/runtime-after.json"
cmp "$out/runtime-before.json" "$out/runtime-after.json"
exit "$overall"
