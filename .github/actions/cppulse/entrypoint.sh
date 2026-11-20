#!/bin/bash
# Local gate adapter over the installed engine. No checkout, API calls or uploads.
set -euo pipefail

invalid() { printf 'cppulse action: %s\n' "$1" >&2; exit 2; }

[[ "${INPUT_POST_COMMENT:-false}" == "false" ]] || invalid 'Comments are not supported by this local adapter.'
[[ -z "${INPUT_BASE_REF:-}" ]] || invalid 'Use an explicit checked baseline; automatic ref checkout is unsupported.'
[[ "${INPUT_GENERATE_PDF:-false}" == "false" ]] || invalid 'Generate reports explicitly with cppulse report --evidence.'
[[ "${INPUT_FAIL_ON_REGRESSION:-false}" == "false" ]] || invalid 'The selected check already supplies the gate; use a finding request for regressions.'
[[ -n "${INPUT_STORE_PATH:-}" ]] || invalid 'store-path is required.'
policy="${INPUT_POLICY_FILE:-}"
findings="${INPUT_FINDING_REQUEST:-}"
[[ -n "$policy" || -n "$findings" ]] || invalid 'Select policy-file or finding-request.'
[[ -z "$policy" || -z "$findings" ]] || invalid 'Select only one policy-file or finding-request.'
run_id="${INPUT_RUN_ID:-}"
manifest_sha="${INPUT_MANIFEST_SHA256:-}"
[[ -z "$run_id" && -z "$manifest_sha" || -n "$run_id" && -n "$manifest_sha" ]] || invalid 'Select both run-id and manifest-sha256, or neither.'

cd -- "${GITHUB_WORKSPACE:-$PWD}"
workspace="$(cd -- "${INPUT_REPO_PATH:-.}" && pwd -P)"
cd -- "$workspace"
command=(cppulse check --store "$INPUT_STORE_PATH" --workspace "$workspace")
if [[ -n "$policy" ]]; then command+=(--policy "$policy"); else command+=(--findings "$findings"); fi
if [[ -n "$run_id" ]]; then command+=(--run-id "$run_id" --manifest-sha256 "$manifest_sha"); fi

# A unique local file preserves machine output without overwriting a prior run.
result="$(mktemp "$workspace/cppulse-check-result.XXXXXX.json")"
status=0
"${command[@]}" > "$result" || status=$?
cat -- "$result"
if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  printf 'exit-code=%s\nresult-path=%s\n' "$status" "$result" >> "$GITHUB_OUTPUT"
fi
exit "$status"
