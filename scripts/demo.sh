#!/usr/bin/env bash
# Native, checkout-based demonstration. Requires built analyzer/CLI and Python deps.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
mkdir -p "$root/tests/tmp"
fixture=$(bash "$root/scripts/prepare_demo_fixture.sh")
output=${1:-"$root/output/demo"}
mkdir -p "$output"
output=$(cd "$output" && pwd)
"$root/cli/build/cppulse" --project-root "$root" analyze --repo "$fixture" --output "$output" --profile default
"$root/cli/build/cppulse" --project-root "$root" report --input "$output" --format json
python3 "$root/scripts/verify_demo.py" "$output"
git -C "$fixture" rev-parse HEAD > "$output/fixture-revision.txt"
(cd "$fixture" && sha256sum clean.cpp intentional.cpp) > "$output/fixture-sources.sha256"
git -C "$fixture" show --no-patch --format=fuller HEAD > "$output/fixture-commit.txt"
printf 'Synthetic fixture: %s\nOutput: %s\n' "$fixture" "$output"
