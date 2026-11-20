#!/usr/bin/env bash
# Compatibility wrapper; the portable runner owns every check and exit status.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
exec "${CPPULSE_PYTHON:-python3}" "$root/scripts/check_local.py" "$@"
