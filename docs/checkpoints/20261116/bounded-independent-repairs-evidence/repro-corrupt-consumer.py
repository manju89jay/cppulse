from pathlib import Path
import json,hashlib
from cppulse.native import NativeInstallation
from cppulse.config import effective_config
import cppulse.pipeline as pipeline
import cppulse.predictor.main as predictor
from cppulse.run_store import RunStore
base=Path('work/repairs-bounded-review/corrupt-consumer').resolve();base.mkdir()
source=base/'source';source.mkdir();(source/'main.cpp').write_text('int value(){return 1;}\n')
resource=base/'resources';(resource/'include').mkdir(parents=True);(resource/'include/stddef.h').write_text('// authored resource fixture\n')
native=NativeInstallation(Path('work/repairs-bounded-review/native-final/cppulse-analyzer').resolve(),resource,(),None)
cfg=effective_config(source,base/'store',execution={'mode':'bounded','jobs':1,'work_directory':str(base/'work'),'wall_seconds':20},history={'enabled':False})
original_discover=pipeline.discover_native;original_predict=predictor.run
seen={}
def corrupt(*args,**kwargs):
 generated=Path(args[1]);seen['generated_directory']=str(generated)
 (generated/'risk_scores.json').write_text('{"health_score":')
 seen['invalid_consumer_artifact_existed']=True
 raise RuntimeError('authored consumer crash after partial JSON write')
try:
 pipeline.discover_native=lambda:native;predictor.run=corrupt
 try:pipeline.analyze(cfg,report_format='json',timeout=60)
 except Exception as error:seen['analysis_exception']=type(error).__name__+': '+str(error)
finally:
 pipeline.discover_native=original_discover;predictor.run=original_predict
try:
 snapshot=RunStore(cfg.output).resolve_latest_attempt()
 seen['published_attempt']=snapshot.run_id
 seen['published_receipt_count']=sum(a.get('contract',{}).get('kind')=='execution_receipt' for a in snapshot.manifest['artifacts'])
except Exception as error:seen['published_attempt']=None;seen['store_error']=type(error).__name__+': '+str(error)
seen['raw_result_count']=len(list((base/'work').rglob('result.json')))
seen['generated_directory_retained']=Path(seen['generated_directory']).exists()
seen['native_sha256']=hashlib.sha256(native.analyzer.read_bytes()).hexdigest()
seen['source_sha256']={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path('python/cppulse/pipeline.py'),Path('python/cppulse/analysis_execution.py')]}
(base/'proof.json').write_text(json.dumps(seen,indent=2)+'\n');print(json.dumps(seen))
