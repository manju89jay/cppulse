from pathlib import Path
import hashlib,json,subprocess,sys,datetime
root=Path('/workspace/cppulse');out=root/'work/query-observation-independent-all-final';out.mkdir(exist_ok=False)
paths=[root/'python/cppulse/query_observation.py',root/'python/cppulse/contracts/query_observation.py',root/'tests/test_query_observation.py',root/'tests/test_query_observation_review.py',root/'tests/test_query_observation_native.py',*sorted((root/'python/cppulse/contracts/schemas/query_observation_private').glob('*.json'))]
def snapshot():return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
before=snapshot();command=[sys.executable,'-m','pytest','-q','tests/test_query_observation.py','tests/test_query_observation_review.py','tests/test_query_observation_native.py','--basetemp','work/query-observation-independent-all-final/pytest']
with (out/'tests.log').open('w') as log:result=subprocess.run(command,cwd=root,stdout=log,stderr=subprocess.STDOUT)
after=snapshot();pins=[]
for p in (out/'pytest').rglob('*'):
 if p.is_file() and not p.is_symlink() and (p.suffix=='.json' or p.name.endswith('.log')):pins.append({'path':str(p.relative_to(root)),'size_bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
record={'recorded_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'command':command,'exit_status':result.returncode,'source_before':before,'source_after':after,'source_stable':before==after,'artifacts':pins,'scope':'Independent finite descriptivequery integrity/parser/receipt review overselectedtrue/strace andcontrolledrawdata. No input closure/cache eligibility/runtime or filesystem provenance/scale/platform/full-plan qualification.'}
(out/'check.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps({'exit_status':result.returncode,'source_stable':before==after,'artifacts':len(pins)}));assert result.returncode==0 and before==after
