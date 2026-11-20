"""Failed TU creation cannot manufacture verified parsed-buffer evidence."""
from copy import deepcopy
import json
from pathlib import Path
from cppulse.analysis import normalize_native_analysis
from tests.test_analysis_inventory import native_snapshot


def test_actual_failed_tu_shape_remains_readable_unknown(tmp_path):
    actual = json.loads(Path('work/coherence-review2/failed-parse/out/findings.json').read_text())
    def mutate(report, root):
        report['metadata']['file_count'] = 0
        report['metadata']['total_loc'] = 0
        report['metadata']['analysis']['files'][0]['status'] = 'failed'
        report['metadata']['analysis']['files'][0]['reason'] = 'libclang failed to create translation unit'
        raw = deepcopy(actual['metadata']['analysis']['native_metrics'])
        raw['files'][0]['path'] = str(root / 'main.cpp')
        report['metadata']['analysis']['native_metrics'] = raw
    frozen, args = native_snapshot(tmp_path, mutate=mutate)
    result = normalize_native_analysis(frozen, **args)
    assert result.inventory['items'][0]['status'] == 'failed'
    assert result.inventory['items'][0].get('buffer_coherence') != 'verified'
