from pathlib import Path
import json,hashlib,shutil
from cppulse.native import NativeInstallation
from cppulse.config import effective_config
from cppulse.analysis_execution import run_analysis
from cppulse.pipeline import _publish_bounded
base=Path('work/repairs-bounded-review/result-mutation').resolve();base.mkdir()
source=base/'source';source.mkdir();(source/'main.cpp').write_text('int value(){return 1;}\n')
resource=base/'resources';(resource/'include').mkdir(parents=True);(resource/'include/stddef.h').write_text('// authored resource fixture\n')
native=NativeInstallation(Path('work/repairs-bounded-review/native-final/cppulse-analyzer').resolve(),resource,(),None)
cfg=effective_config(source,base/'store',execution={'mode':'bounded','jobs':1,'work_directory':str(base/'work'),'wall_seconds':20},history={'enabled':False})
execution=run_analysis(cfg,native,base/'work',timeout=60)
unit,result=execution.results[0];path=Path(unit['work_root'])/'result.json';before=path.read_bytes();(base/'original-result.json').write_bytes(before)
mutated=json.loads(before);mutated['execution_receipt']['reason']='deliberate changed receipt in raw result after execution';path.write_text(json.dumps(mutated,indent=2)+'\n')
generated=base/'generated';generated.mkdir();shutil.copy2(execution.report_path,generated/'findings.json')
snapshot=_publish_bounded(cfg,execution,generated,complete=False,failure=RuntimeError('explicit original-result integrity fixture'))
binding=json.loads(snapshot.read_bytes('analysis-bindings'))['units'][0]
retained=json.loads(snapshot.read_bytes(binding['result_artifact_id']));receipt=snapshot.read_json(binding['receipt_artifact_id'])
record=next(a for a in snapshot.manifest['artifacts'] if a['id']==binding['result_artifact_id'])
proof={'qualification':'Deliberate post-execution valid JSON corruption; real original native execution and bytes retained separately','source_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path('python/cppulse/pipeline.py'),Path('python/cppulse/analysis_execution.py')]},'native_sha256':hashlib.sha256(native.analyzer.read_bytes()).hexdigest(),'published_run_id':snapshot.run_id,'published_status':snapshot.manifest['status'],'embedded_receipt_matches_standalone':retained['execution_receipt']==receipt,'summary_original_result_sha256':execution.summary['results'][0]['sha256'],'retained_result_sha256':record['sha256'],'expected_original_result_sha256':hashlib.sha256(before).hexdigest()}
(base/'proof.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))
