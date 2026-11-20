from pathlib import Path
import json,hashlib
from cppulse.native import NativeInstallation
from cppulse.config import effective_config
from cppulse.analysis_execution import run_analysis
base=Path('work/repairs-bounded-review/receipt-resume').resolve();base.mkdir()
source=base/'source';source.mkdir();(source/'main.cpp').write_text('int value(){return 1;}\n')
resource=base/'resources';(resource/'include').mkdir(parents=True);(resource/'include/stddef.h').write_text('// authored resource fixture\n')
native=NativeInstallation(Path('work/repairs-bounded-review/native-final/cppulse-analyzer').resolve(),resource,(),None)
cfg=effective_config(source,base/'store',execution={'mode':'bounded','jobs':1,'work_directory':str(base/'work'),'wall_seconds':20},history={'enabled':False})
first=run_analysis(cfg,native,base/'unused',timeout=60)
unit,result=first.results[0];path=Path(unit['work_root'])/'result.json';(base/'original-result.json').write_bytes(path.read_bytes())
mutated=json.loads(path.read_bytes());mutated['execution_receipt']['id']='deliberately-replaced-receipt-identity';path.write_text(json.dumps(mutated,indent=2)+'\n')
cfg.execution['resume']=True
second=run_analysis(cfg,native,base/'unused2',timeout=60)
proof={'qualification':'Deliberate valid-JSON checkpoint receipt-ID mutation after actual successful native execution','first_receipt_id':result['execution_receipt']['id'],'second_receipt_id':second.results[0][1]['execution_receipt']['id'],'second_summary':second.summary,'same_request':unit==second.results[0][0],'native_sha256':hashlib.sha256(native.analyzer.read_bytes()).hexdigest(),'source_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path('python/cppulse/analysis_execution.py'),Path('python/cppulse/work_units.py')]}}
(base/'proof.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps({'first':proof['first_receipt_id'],'second':proof['second_receipt_id'],'status':second.summary['status'],'resumed':second.summary['resumed_units']}))
