from pathlib import Path
from copy import deepcopy
import hashlib,json,sys
sys.path.insert(0,'python')
from cppulse.service_repair import validate_report
from cppulse.errors import ContractError,IntegrityError
p=Path('python/cppulse/service_repair.py');before=hashlib.sha256(p.read_bytes()).hexdigest();root=Path('work/service-independent-review/transient-tools/observations').absolute();request=json.loads((root/'request.json').read_bytes());report=json.loads((root/'report.json').read_bytes());forged=deepcopy(report);outcome=forged['steps'][0]['outcome'];outcome['stdout_bytes']-=1;outcome['stderr_bytes']+=1
rejected=False
try:validate_report(request,forged,root)
except (ContractError,IntegrityError):rejected=True
proof={'source_before_sha256':before,'source_after_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'contradictory_stream_counts_rejected':rejected,'observed_metadata':forged['steps'][0]['outcome'],'retained_stdout_bytes':forged['steps'][0]['stdout']['size_bytes'],'retained_stderr_bytes':forged['steps'][0]['stderr']['size_bytes'],'original_progress_unchanged':True}
Path('work/service-independent-review/stream-counts-proof.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof,indent=2));assert rejected,'Service assessment accepted stdout/stderr counts contradicting retained log bytes'
