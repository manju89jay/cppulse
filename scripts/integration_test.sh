#!/usr/bin/env bash
# Local Compose integration: successful one-shot exits are expected.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"
if ! command -v docker >/dev/null || ! docker compose version; then
  echo 'BLOCKED: Docker with Compose v2 is required; no Compose checks passed.' >&2
  exit 2
fi
mkdir -p tests/tmp output
export REPO_PATH=${REPO_PATH:-$(bash scripts/prepare_demo_fixture.sh)}
export OUTPUT_PATH=${OUTPUT_PATH:-./output/compose-demo}
mkdir -p "$OUTPUT_PATH"
trap 'docker compose logs --no-color; docker compose down' EXIT
docker compose up --build -d
for service in analyzer-core git-miner predictor report-pdf; do
  container=$(docker compose ps -aq "$service")
  test -n "$container"
  code=$(timeout 180 docker wait "$container")
  test "$code" = 0 || { echo "FAIL: $service exited $code"; exit 1; }
done
curl --fail --retry 20 --retry-connrefused --retry-delay 1 http://localhost:8000/api/v1/summary
curl --fail http://localhost:3000/api/v1/findings
python3 scripts/verify_pipeline.py "$OUTPUT_PATH" --require-pdf
echo 'PASS: Compose pipeline, API proxy, contracts and PDF'
