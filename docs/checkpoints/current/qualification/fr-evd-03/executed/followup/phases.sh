#!/usr/bin/env bash
set -euo pipefail
lane=/workspace/work/current38-batch14/no-false-followup
python=/workspace/cppulse/.venv/bin/python
out=$1
"$python" -B "$lane/run.py" before "$out"
overall=0
for name in show-only empty contradictory unsupported; do
  phase="$out/$name"
  mkdir "$phase" "$phase/outside"
  status=0
  "$python" -B "$lane/run.py" "$name" "$phase" > "$phase/phase.stdout" 2> "$phase/phase.stderr" || status=$?
  printf '%d\n' "$status" > "$phase/phase.exit"
  printf '%s exit %d\n' "$name" "$status"
  if (( status != 0 )); then tail -35 "$phase/phase.stderr"; overall=$status; fi
done
"$python" -B "$lane/run.py" after "$out"
cmp "$out/custody-before.json" "$out/custody-after.json"
exit "$overall"
