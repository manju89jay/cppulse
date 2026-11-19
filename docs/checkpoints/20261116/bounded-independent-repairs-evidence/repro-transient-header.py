from pathlib import Path
import json,os,hashlib
import cppulse.analysis_execution as ae
from cppulse.native import NativeInstallation
from cppulse.config import effective_config
base=Path('work/repairs-bounded-review/transient-header').resolve();base.mkdir()
source=base/'source';source.mkdir()
h=source/'a.hpp';original=b'#define BRANCH 0\n';h.write_bytes(original)
(source/'main.cpp').write_text('#include "a.hpp"\nint value(int x) {\n#if BRANCH\n if(x) return 1;\n#endif\n return 0;\n}\n')
config=effective_config(source,base/'store',execution={'mode':'bounded','jobs':1,'wall_seconds':20,'address_space_bytes':2147483648,'cpu_seconds':20},history={'enabled':False})
native=NativeInstallation(Path('work/repairs-bounded-review/native-final/cppulse-analyzer').resolve(),Path(os.environ['CPPULSE_CLANG_RESOURCE_DIR']),(),None)
original_execute=ae.execute_work_units
active=False
changes=[]
def execute(units,**kwargs):
 global active
 def selected():
  global active
  for unit in units:
   if unit['primary_file']=='main.cpp':
    h.write_text('#define BRANCH 1\n');active=True
    changes.append({'when':'before_native_main','sha256':hashlib.sha256(h.read_bytes()).hexdigest()})
   yield unit
 for execution in original_execute(selected(),**kwargs):
  if active:
   h.write_bytes(original);active=False
   changes.append({'when':'after_native_main_before_global_guard','sha256':hashlib.sha256(h.read_bytes()).hexdigest()})
  yield execution
try:
 ae.execute_work_units=execute
 run=ae.run_analysis(config,native,base/'work',timeout=60)
finally:
 ae.execute_work_units=original_execute
 h.write_bytes(original)
clean=ae.run_analysis(config,native,base/'clean-work',timeout=60)
a=json.loads(run.report_path.read_text());b=json.loads(clean.report_path.read_text())
def metrics(report):return next(r for r in report['metadata']['analysis']['native_metrics']['files'] if Path(r['path']).name=='main.cpp')['functions']
proof={'qualification':'Intentional transient selected-header mutation around actual native execution, restored before final guards','native_sha256':hashlib.sha256(native.analyzer.read_bytes()).hexdigest(),'summary':run.summary,'manifest_source_digest':run.source['digest'],'current_source_same_as_clean':run.source==clean.source,'source_current_bytes':h.read_text(),'transient_functions':metrics(a),'clean_functions':metrics(b),'changes':changes,'source_files':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path('python/cppulse/analysis_execution.py'),Path('python/cppulse/work_units.py')]}}
(base/'proof.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps(proof))
