"""Independent exact current integration repair gate, without acceptance claims."""
from pathlib import Path
import datetime,hashlib,json,os,platform,shutil,subprocess,sys,time
ROOT=Path('/workspace/cppulse');OUT=ROOT/'work/integration-contract-independent'
modules=['tests/test_integration_contract_review.py','tests/test_findings.py','tests/test_repairs.py','tests/test_finding_workflows.py','tests/test_repair_cli.py','tests/test_native_analysis_context_contract.py','tests/test_assessment_workflows.py','tests/test_policy_profile12_presentation.py','tests/test_public_workflows.py','tests/test_public_cli.py','tests/test_public_workflow_contracts.py']
reviewed=['python/cppulse/workflows.py','python/cppulse/contracts/public_workflows.py','python/cppulse/contracts/validation.py','python/cppulse/analysis.py','python/cppulse/findings.py','python/cppulse/repairs.py','python/cppulse/presentation.py','tests/native_buffer_fixture.py','tests/test_analysis_inventory.py','tests/test_maintenance_metrics_contract.py','tests/test_snapshot_view_contract.py','docs/schemas/findings.schema.json',*modules]
reviewed += [str(p.relative_to(ROOT)) for group in ('v2','prototype_v1') for p in sorted((ROOT/'python/cppulse/contracts/schemas'/group).glob('*.json'))]
shared=['python/cppulse/run_store.py','python/cppulse/store_coordination.py','python/cppulse/store_recovery.py',*[str(p.relative_to(ROOT)) for p in sorted((ROOT/'python/cppulse/contracts/schemas/store_private').glob('*.json'))]]
def hashes(paths):return {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sorted(set(paths))}
before=hashes(reviewed);shared_before=hashes(shared)
compiler=Path(shutil.which('g++')).resolve();compiler_info=subprocess.run([str(compiler),'--version'],capture_output=True,text=True,timeout=5)
command=[sys.executable,'-m','pytest','-q',*modules,'--basetemp','/tmp/cppulse-independent-integration-20261116']
started=datetime.datetime.now(datetime.timezone.utc).isoformat()
with (OUT/'tests.log').open('w') as log:result=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
after=hashes(reviewed);shared_after=hashes(shared)
base=Path('/tmp/cppulse-independent-integration-20261116');pins=[]
for p in sorted(base.rglob('run_manifest.json')):
 raw=p.read_bytes();m=json.loads(raw);pins.append({'path':str(p),'sha256':hashlib.sha256(raw).hexdigest(),'run_id':m['run_id'],'status':m['status'],'source_digest':m['source']['digest']})
record={'started_utc':started,'finished_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'argv':command,'exit_status':result.returncode,'reviewed_before':before,'reviewed_after':after,'reviewed_source_stable':before==after,'shared_before':shared_before,'shared_after':shared_after,'shared_source_stable':shared_before==shared_after,'source_stable':before==after and shared_before==shared_after,'compiler':{'path':str(compiler),'sha256':hashlib.sha256(compiler.read_bytes()).hexdigest(),'version':compiler_info.stdout,'scope':'Selected actual C++ compile/run controls; helper/runtime closure not attested.'},'environment':{'python':sys.version,'platform':platform.platform()},'retained_run_manifests':pins,'limits':'Scoped independent verification, including explicitly synthetic metadata fixtures and actual C++ compilation controls. Not native detector accuracy, complete source-suite, platform, benchmark or full-plan acceptance.'}
(OUT/'check.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps({'exit_status':result.returncode,'source_stable':record['source_stable'],'retained_manifests':len(pins)}))
