#!/usr/bin/env bash
# Create an explicitly synthetic, local-only Git fixture using real current time.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
mkdir -p "$root/tests/tmp"
fixture=$(mktemp -d "$root/tests/tmp/demo-XXXXXX")
cp "$root"/demo/fixture/*.cpp "$fixture/"
git -C "$fixture" init -q
git -C "$fixture" add clean.cpp intentional.cpp
git -C "$fixture" -c user.name='cppulse Synthetic Fixture Automation' -c user.email='fixture@example.invalid' commit -q -m 'Synthetic demo: clean code and intentional rule triggers'
printf '%s\n' "$fixture"
