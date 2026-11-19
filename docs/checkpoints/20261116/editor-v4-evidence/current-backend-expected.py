import json
from pathlib import Path
import subprocess
import sys

import cppulse

root = Path('/workspace/cppulse')
cases = json.loads((root / 'work/editor-current-backend/cases.json').read_text())
rows = []
for case in cases:
    command = [sys.executable, '-I', '-m', 'cppulse', 'explain', '--store', case['store'], '--run-id', case['run_id'], '--manifest-sha256', case['manifest_sha256']]
    result = subprocess.run(command, cwd='/tmp', text=True, capture_output=True, check=True)
    view = json.loads(result.stdout)
    wrapper = next(row for row in view['facts'] if row['kind'] == 'maintenance_health')
    health = json.loads(wrapper['raw_json'], parse_int=str, parse_float=str)
    rows.append({**case, 'source_digest': view['source']['digest'], 'artifact_id': wrapper['artifact_id'], 'sha256': wrapper['sha256'], 'size_bytes': wrapper['size_bytes'], 'overall': health['aggregate']['overall'], 'availability': health['aggregate']['availability'], 'scorer_id': health['scorer']['id'], 'scorer_version': health['scorer']['version'], 'configuration_digest': health['scorer']['configuration_digest'], 'requires_buffer_coherence': health['scorer']['requires_buffer_coherence']})
output = {'origin': cppulse.__file__, 'python': sys.executable, 'cases': rows}
(root / 'work/editor-current-backend/expected.json').write_text(json.dumps(output, indent=2) + '\n')
print(json.dumps({'origin': cppulse.__file__, 'cases': len(rows)}))
