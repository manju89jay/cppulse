#!/bin/sh
# Consume the exact same resolved configuration as the native stage.
set -eu
if [ -n "${CPPULSE_PROFILE:-}" ]; then
    echo 'Resolve --profile with cppulse config --native-output and select that CPPULSE_CONFIG in both stages' >&2
    exit 2
fi
# Matched finite discovery only at the container orchestration boundary.
# The standalone predictor still performs no implicit discovery.
if [ -z "${CPPULSE_CONFIG:-}" ]; then
    discovered=''
    for candidate in "${CPPULSE_REPO_ROOT:-/repo}/.cppulserc.json" "${CPPULSE_REPO_ROOT:-/repo}/.cppulserc.yml" "${CPPULSE_REPO_ROOT:-/repo}/.cppulserc.yaml"; do
        if [ -f "$candidate" ]; then
            if [ -n "$discovered" ]; then
                echo 'Ambiguous project configurations; select one shared CPPULSE_CONFIG explicitly' >&2
                exit 2
            fi
            discovered=$candidate
        fi
    done
    CPPULSE_CONFIG=$discovered
fi
if [ -n "${CPPULSE_CONFIG:-}" ]; then
    case "$CPPULSE_CONFIG" in /*) ;; *) echo 'CPPULSE_CONFIG must be an absolute container path' >&2; exit 2;; esac
fi
if [ -n "${CPPULSE_CONFIG:-}" ]; then
    exec python3 -m cppulse.predictor.main --config "$CPPULSE_CONFIG" "$@"
else
    exec python3 -m cppulse.predictor.main "$@"
fi
