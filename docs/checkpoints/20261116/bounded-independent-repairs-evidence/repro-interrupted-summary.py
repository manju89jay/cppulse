from pathlib import Path
import json,hashlib
from cppulse.native import NativeInstallation
from cppulse.config import effective_config
from cppulse.analysis_execution import run_analysis
base=Path('work/repairs-bounded-review/interrupted-summary').resolve();base.mkdir()
source=base/'source';source.mkdir();(source/'main.cpp').write_text('int value(){return 1;}\n')
resource=base/'resources';(resource/'include').mkdir(parents=True);(resource/'include/stddef.h').write_text('// authored resource fixture\n')
native=NativeInstallation(Path('work/repairs-bounded-review/native-final/cppulse-analyzer').resolve(),resource,(),None)
cfg=effective_config(source,base/'store',execution={'mode':'bounded','jobs':1,'work_directory':str(base/'work'),'wall_seconds':20},history={'enabled':False})
first=run_analysis(cfg,native,base/'unused',timeout=60)
first.summary_path.rename(base/'original-summary.json')
unit,result=first.results[0];path=Path(unit['work_root'])/'result.json';(base/'original-result.json').write_bytes(path.read_bytes())
changed=json.loads(path.read_bytes());changed['reason']=changed['execution_receipt']['reason']='deliberate post-crash mutation';path.write_text(json.dumps(changed))
cfg.execution['resume']=True
second=run_analysis(cfg,native,base/'unused2',timeout=60)
proof={'qualification':'Actual unit completed; missing coordinator summary simulated by preserving/renaming it, then valid-JSON checkpoint metadata corruption','status':second.summary['status'],'results':len(second.results),'corrupt_receipt_registered':any(r['execution_receipt']==changed['execution_receipt'] for _,r in second.results),'limitations':second.summary['limitations'],'native_sha256':hashlib.sha256(native.analyzer.read_bytes()).hexdigest(),'source_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path('python/cppulse/analysis_execution.py'),Path('python/cppulse/work_units.py')]}}
(base/'proof.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))
