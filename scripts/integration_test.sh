#!/bin/bash
set -e

echo "=== cppulse Integration Test ==="

# Use the project's own test fixtures as the target repo
export REPO_PATH=${REPO_PATH:-./analyzer-core/tests/fixtures}

# Run the full pipeline
echo "Starting docker-compose pipeline..."
docker-compose up --build --abort-on-container-exit

# Verify outputs exist
echo ""
echo "=== Verifying output files ==="
for f in findings.json git_metrics.json risk_scores.json roadmap.json; do
    if [ ! -f "./output/$f" ]; then
        echo "FAIL: output/$f not found"
        exit 1
    fi
    echo "PASS: output/$f exists"
done

# Verify JSON schemas
echo ""
echo "=== Validating JSON schemas ==="
python3 -c "
import json, jsonschema

pairs = [
    ('docs/schemas/findings.schema.json', 'output/findings.json'),
    ('docs/schemas/git_metrics.schema.json', 'output/git_metrics.json'),
    ('docs/schemas/risk_scores.schema.json', 'output/risk_scores.json'),
    ('docs/schemas/roadmap.schema.json', 'output/roadmap.json'),
]

for schema_file, data_file in pairs:
    with open(schema_file) as s, open(data_file) as d:
        jsonschema.validate(json.load(d), json.load(s))
    print(f'PASS: {data_file} validates against {schema_file}')
"

echo ""
echo "=== All integration tests passed ==="
