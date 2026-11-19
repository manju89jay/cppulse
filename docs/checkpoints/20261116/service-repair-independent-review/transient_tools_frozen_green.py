from pathlib import Path
import hashlib,json,runpy,sys
sys.path.insert(0,'python')
source_files=[Path('python/cppulse/service_repair.py'),*Path('python/cppulse/contracts/schemas/service_repair_private').glob('*.json')]
def source_hashes():return {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files}
source_before=source_hashes()
from cppulse.service_repair import verify_service_proposal,validate_report
helpers=runpy.run_path('tests/test_service_repair.py');pin=helpers['pin']
r=Path('/workspace/cppulse/work/service-independent-review/sealed-transient-tools-v2');r.mkdir(exist_ok=False)
q=helpers['_request'](r);compiler=r/'selected-compiler';marker=r/'unselected-tool-executed';counter=r/'inspect-count'
original='#!/usr/bin/python3\nimport os,sys\nos.execv("/usr/bin/g++",["/usr/bin/g++",*sys.argv[1:]])\n'
changed='#!/usr/bin/python3\nimport os,sys\nopen('+repr(str(marker))+',"a").write("changed\\n")\nos.execv("/usr/bin/g++",["/usr/bin/g++",*sys.argv[1:]])\n'
compiler.write_text(original);compiler.chmod(0o700)
inspected=json.loads(__import__('subprocess').check_output([q['docker']['path']]))
docker=Path(q['docker']['path']);docker.write_text('#!/usr/bin/python3\nfrom pathlib import Path\nimport json\nc=Path('+repr(str(counter))+')\nn=int(c.read_text()) if c.exists() else 0\nc.write_text(str(n+1))\nPath('+repr(str(compiler))+').write_text('+repr(changed)+' if n==0 else '+repr(original)+')\nprint('+repr(json.dumps(inspected))+')\n')
q['compiler']=pin(compiler);q['docker']=pin(docker)
(r/'selected-request.json').write_text(json.dumps(q,indent=2)+'\n')
report=verify_service_proposal(q,r/'observations',execute_trusted_project=True);validate_report(q,report,r/'observations')
proof={'source_before':source_before,'source_after':source_hashes(),'source_stable':source_before==source_hashes(),'report_status':report['status'],'original_selected_tool_restored':pin(compiler)==q['compiler'],'retained_copy_matches_selected_pin':hashlib.sha256((r/'observations/inputs/tools/compiler').read_bytes()).hexdigest()==q['compiler']['sha256'],'unselected_tool_was_actually_executed':marker.exists(),'actual_unselected_calls':marker.read_text().splitlines() if marker.exists() else [],'limitation':'Synthetic controlled inspector and tiny genuine ELF compiles, not actual Mongo service identity.'}
(r/'proof.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof,indent=2))
assert report['status']=='verified_finite_regression'
assert not marker.exists(),'Unselected compiler bytes executed despite sealed selection'
assert source_before==source_hashes(),'Source changed during actual check'
