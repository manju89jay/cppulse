"""Actual authored C++ producer-to-measured-consumer execution, not corpus proof."""
import json
from pathlib import Path
import subprocess
import sys
sys.path.insert(0, str(Path('scripts').resolve()))
from demo_policy import inspect_tools, prepare_workspace, NATIVE_JOB
from demo_evidence import make_request
from cppulse.identities import snapshot_inputs
from cppulse.maintenance import persist_maintenance_health
from cppulse.presentation import build_snapshot_view, render_snapshot_html, render_snapshot_pdf
from cppulse.run_store import RunStore
from cppulse.tooling import load_rule_registry

root = Path('work/measured-actual').resolve()
root.mkdir(exist_ok=True)
tools = inspect_tools(Path('analyzer-core/build-cloud-resume/cppulse-analyzer').resolve(), Path('work/native-deps/usr/lib/llvm-19/lib/clang/19').resolve())
summary = []
for scenario in ('clean', 'findings'):
    directory = root / scenario
    directory.mkdir()
    workspace, source, resources = prepare_workspace(directory, Path('demo/policy-fixture').resolve(), Path(tools['resource_directory']), scenario)
    request = make_request(scenario, workspace, source, resources, tools)
    request['normalizers'][0]['requested_rules'] = [row['id'] for row in load_rule_registry()['rules']]
    request_path = directory / 'request.json'
    request_path.write_text(json.dumps(request, indent=2)+'\n')
    store = RunStore(directory / 'store')
    argv = [sys.executable, '-m', 'cppulse', 'collect', '--request', str(request_path), '--workspace', str(workspace), '--store', str(store.root)]
    result = subprocess.run(argv, capture_output=True, text=True, timeout=180)
    (directory / 'collect.stdout.json').write_text(result.stdout)
    (directory / 'collect.stderr.log').write_text(result.stderr)
    collected = json.loads(result.stdout)
    if not collected.get('final_run') or collected['normalizers'][0]['status'] != 'completed':
        raise RuntimeError(f'Collection failed: {collected}')
    pin = collected['final_run']
    snapshot = store.open_run(pin['run_id'], manifest_sha256=pin['manifest_sha256'])
    measured = persist_maintenance_health(snapshot, workspace=workspace, store=store, required_context_ids=[NATIVE_JOB])
    metrics = [measured.read_json(row['id']) for row in measured.manifest['artifacts'] if row.get('contract', {}).get('kind') == 'analysis_metrics']
    health = [measured.read_json(row['id']) for row in measured.manifest['artifacts'] if row.get('contract', {}).get('kind') == 'maintenance_health'][0]
    assert health['aggregate']['availability'] == 'scored', health
    assert metrics and any(row['metric'] == 'cyclomatic_complexity' for row in metrics[0]['items'])
    view = build_snapshot_view(measured)
    html = render_snapshot_html(view)
    assert 'Measured maintenance health' in html
    (directory / 'measured.html').write_text(html)
    pdf = render_snapshot_pdf(view)
    assert pdf.startswith(b'%PDF') and len(pdf) > 1000
    (directory / 'measured.pdf').write_bytes(pdf)
    (directory / 'health.json').write_text(json.dumps(health, indent=2)+'\n')
    record = {'scenario':scenario, 'workspace':str(workspace), 'store':str(store.root), 'run_id':measured.run_id, 'manifest_sha256':measured.manifest_sha256, 'job_context_id':NATIVE_JOB, 'metric_cells':len(metrics[0]['items']), 'health':health['aggregate'], 'pdf_bytes':len(pdf)}
    summary.append(record)
    print(json.dumps(record), flush=True)
(root / 'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
