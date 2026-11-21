#!/usr/bin/env bash
set -euo pipefail
lane=/workspace/work/roadmap-order-qualification/governance-refresh
out=$(/usr/bin/realpath -m "$1")
[[ "$(/usr/bin/dirname "$out")" == "$lane" ]]
/usr/bin/mkdir "$out"
set +e
/usr/bin/python3.13 -I -B "$lane/refresh.py" run "$out" > "$out/observer.stdout" 2> "$out/observer.stderr"
status=$?
set -e
printf '%s\n' "$status" > "$out/observer.exit"
exit "$status"
