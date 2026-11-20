from pathlib import Path
import hashlib,importlib.resources,json,os,subprocess,sys,zipfile
import cppulse
import cppulse.service_repair as service
from cppulse.client_contract import capabilities

root=Path('/workspace/cppulse')
base=root/'work/semantic-service-installed-current'
wheel=root/'work/cloud-resume/wheel-typed-sdk-service-current/wheels/cppulse-0.2.0.dev2-py3-none-any.whl'
venv=root/'work/cloud-resume/installed-typed-sdk-service-current/core-venv'
expected_wheel='60fabb121d6ed87bbb7b400a7d4ac6e3b56060346c8d04f16d38c960d19f7d4e'
def sha(path):
 with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
assert sha(wheel)==expected_wheel
package=Path(cppulse.__file__).resolve().parent
assert package.is_relative_to(venv.resolve())
selected=['service_repair.py','cli.py','client_contract.py','execution.py','run_store.py','identities.py','errors.py','contracts/validation.py','contracts/schemas/service_repair_private/request.schema.json','contracts/schemas/service_repair_private/report.schema.json']
files={}
with zipfile.ZipFile(wheel) as z:
 for name in selected:
  path=package/name
  expected=hashlib.sha256(z.read('cppulse/'+name)).hexdigest()
  assert sha(path)==expected
  files['cppulse/'+name]={'installed_path':str(path),'sha256':expected}
assert 'verify-service-proposal' in capabilities()['commands']
actual=root/'work/semantic-service-contracts/poco-typed-sealed-current'
request=json.loads((actual/'request.json').read_bytes())
report=json.loads((actual/'report.json').read_bytes())
service.validate_report(request,report,actual)
assert report['status']=='verified_finite_regression'
commands=[]
def run(argv,label,expected):
 p=subprocess.run(argv,cwd='/tmp',env=dict(os.environ),capture_output=True,text=True,timeout=90)
 (base/(label+'.stdout')).write_text(p.stdout)
 (base/(label+'.stderr')).write_text(p.stderr)
 commands.append({'argv':argv,'cwd':'/tmp','exit_status':p.returncode,'expected':expected,'stdout_sha256':sha(base/(label+'.stdout')),'stderr_sha256':sha(base/(label+'.stderr'))})
 assert p.returncode==expected,(p.returncode,p.stdout,p.stderr)
 return p
refused=base/'refused-no-trusted-opt-in'
run([sys.executable,'-I','-m','cppulse','verify-service-proposal','--request',str(base/'request.json'),'--output',str(refused)],'refusal',2)
assert not refused.exists()
output=base/'public-cli-actual'
run([sys.executable,'-I','-m','cppulse','verify-service-proposal','--request',str(base/'request.json'),'--output',str(output),'--execute-trusted-project'],'public-cli',0)
request=json.loads((base/'request.json').read_bytes())
report=json.loads((output/'report.json').read_bytes())
service.validate_report(request,report,output)
assert report['status']=='verified_finite_regression'
assert len(report['steps'])==10
assert report['steps'][4]['outcome']['returncode']==1
assert report['steps'][8]['outcome']['returncode']==0
for fact in files.values():assert sha(fact['installed_path'])==fact['sha256']
proof={'wheel':str(wheel),'wheel_sha256':expected_wheel,'python':sys.executable,'python_version':sys.version,'cwd':os.getcwd(),'isolated':sys.flags.isolated,'python_path':sys.path,'package_origin':str(package),'installed_files':files,'source_overrides_absent':not any(key in os.environ for key in ('PYTHONPATH','PYTHONHOME','NODE_PATH')) and not any(key.startswith('CPPULSE_') for key in os.environ),'actual_current_poco_retained_report_replayed':True,'actual_current_poco_report_sha256':sha(actual/'report.json'),'actual_current_poco_report_status':'verified_finite_regression','public_cli_status':report['status'],'public_cli_report_sha256':sha(output/'report.json'),'public_cli_test_counts':{'before':{'passed':2,'failed':1},'after':{'passed':3,'failed':0},'skipped':0},'commands':commands,'qualification':'Actual exact-wheel installed Python-I publicwrapper +genuine tiny C++17 ELF relink before/after with explicitly synthetic controlled inspector. Actual current source-bound realPoco report replay checked allretained artifactbytes; this is not a second full installedPoco execution or fullM9/P11/P14 acceptance. Allfilehashes match exactwheel; toolchainhelper/cgroup/stateisolation/semantic-equivalence remain unverified/false.'}
(base/'verification.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps(proof,indent=2))
