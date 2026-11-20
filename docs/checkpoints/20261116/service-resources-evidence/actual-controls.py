from pathlib import Path
import hashlib,json,sys,subprocess,time,datetime
from cppulse.service_repair import _EXEC_CLEAN
from cppulse.service_resources import RESOURCE_EXEC,validate_resource_receipt
root=Path('/workspace/cppulse');base=root/'work/service-resource-actual-controls';base.mkdir(exist_ok=False)
probe=root/'work/service-resource-sourcebound-reviewed/resource-native0/probe'
source=probe.with_suffix('.cpp')
paths=[root/'python/cppulse/service_repair.py',root/'python/cppulse/service_resources.py',source,probe,Path(__file__).absolute(),*sorted((root/'python/cppulse/contracts/schemas/service_repair_private').glob('*.json'))]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def snapshot():return {str(p):sha(p) for p in paths}
before=snapshot();rows=[]
for name,cpu,memory,mode,expected in [('cpu-soft',[1,2],None,'soft',78),('cpu-hard',[1,2],None,'hard',-9),('as-capped',None,67108864,'memory',42),('as-inherited',None,None,'memory',0)]:
 directory=base/name;directory.mkdir();path=directory/'resources.json';limits={'cpu_seconds':cpu,'address_space_bytes':memory}
 command=[sys.executable,'-I','-c',RESOURCE_EXEC+_EXEC_CLEAN,json.dumps(limits),str(path),name,str(probe),mode]
 start=time.monotonic();result=subprocess.run(command,capture_output=True,timeout=10);wall=time.monotonic()-start
 (directory/'stdout.log').write_bytes(result.stdout);(directory/'stderr.log').write_bytes(result.stderr)
 receipt=json.loads(path.read_bytes());validate_resource_receipt(receipt,limits,step_id=name,argv=[str(probe),mode]);assert result.returncode==expected
 rows.append({'name':name,'command':command,'returncode':result.returncode,'expected_returncode':expected,'wall_seconds_single_observation':wall,'resource_receipt':receipt,'resource_sha256':sha(path),'stdout_sha256':sha(directory/'stdout.log'),'stderr_sha256':sha(directory/'stderr.log')})
after=snapshot();assert before==after
record={'recorded_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_before':before,'source_after':after,'source_stable':before==after,'native_source_sha256':sha(source),'native_executable_sha256':sha(probe),'cases':rows,'scope':'Actual Linux per-process CPU/AS controlled observations. Signal alone does not diagnose arbitrary process deaths; no aggregate CPU/RSS/cgroup/PID/security/network or performance-budget claim.'}
(base/'verification.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps({'passed':len(rows),'source_stable':True}))
