from pathlib import Path
import datetime, hashlib, json, subprocess
root=Path.cwd(); out=root/'work/store-heads-v3-current'
paths=['python/cppulse/run_store.py','python/cppulse/store_heads.py','python/cppulse/store_coordination.py','python/cppulse/store_recovery.py','python/cppulse/pipeline.py']
paths += [str(p) for p in Path('python/cppulse/contracts/schemas/store_private').glob('*.json')]
paths += ['tests/test_run_store_v2.py','tests/test_store_heads_v3.py','tests/test_store_heads_v3_contract.py','tests/test_store_recovery.py','tests/test_store_recovery_review.py','tests/test_store_recovery_reconcile.py']
def pins(): return {p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths}
before=pins();cmd=['.venv/bin/python','-m','pytest','-q']+[p for p in paths if p.startswith('tests/')]+['--basetemp','/tmp/cppulse-v3-sourcebound-20261116']
with (out/'pytest.log').open('w') as log:r=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT)
after=pins()
(out/'verification.json').write_text(json.dumps({'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'command':cmd,'exit_status':r.returncode,'before':before,'after':after,'source_stable':before==after,'scope':'Explicit v3 only; default remains v2 pending consumer/default rollout. Original v2 assertions unchanged. Includes real owned subprocess SIGKILL head and migration boundaries; not full production acceptance.'},indent=2)+'\n')
print(r.returncode)
