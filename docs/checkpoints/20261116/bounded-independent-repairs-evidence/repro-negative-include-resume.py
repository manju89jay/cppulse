from pathlib import Path
import json,hashlib
from cppulse.native import NativeInstallation
from cppulse.config import effective_config
from cppulse.analysis_execution import run_analysis
base=Path('work/repairs-bounded-review/negative-include-resume').resolve();base.mkdir()
source=base/'source';source.mkdir();external=base/'external';external.mkdir();query=external/'feature.hpp'
(source/'main.cpp').write_text('int value(int x){\n#if __has_include("'+str(query)+'")\n if(x) return 1;\n#endif\n return 0;\n}\n')
resource=base/'resources';(resource/'include').mkdir(parents=True);(resource/'include/stddef.h').write_text('// authored resource fixture\n')
native=NativeInstallation(Path('work/native-include-buffer-candidate/9004df27f73a73901e3c231834628c24009ffded1730e598754acd6e7c7a6373/cppulse-analyzer').resolve(),resource,(),None)
def config(work,resume):return effective_config(source,base/'store',execution={'mode':'bounded','jobs':1,'work_directory':str(work),'wall_seconds':20,'resume':resume},history={'enabled':False})
first=run_analysis(config(base/'work',False),native,base/'unused',timeout=60)
query.write_text('// external query now succeeds\n')
resumed=run_analysis(config(base/'work',True),native,base/'unused2',timeout=60)
clean=run_analysis(config(base/'clean-work',False),native,base/'unused3',timeout=60)
def data(r):
 unit,outcome=r.results[0];doc=json.loads((Path(unit['work_root'])/'output/findings.json').read_bytes());m=doc['metadata']['analysis']['native_metrics']['files'][0]
 return {'summary':r.summary,'includes':m['includes'],'functions':m['functions'],'receipt_id':outcome['execution_receipt']['id']}
a,b,c=data(first),data(resumed),data(clean)
proof={'qualification':'Actual C++17 __has_include query without an inclusion; external file becomes present between warm resume and fresh clean execution','native_sha256':hashlib.sha256(native.analyzer.read_bytes()).hexdigest(),'first':a,'resumed':b,'clean':c,'all_source_same':first.source==resumed.source==clean.source,'source_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path('python/cppulse/analysis_execution.py'),Path('python/cppulse/work_units.py')]}}
(base/'proof.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps({'source_same':proof['all_source_same'],'first_complexity':a['functions'][0]['cyclomatic_complexity'],'resumed_complexity':b['functions'][0]['cyclomatic_complexity'],'clean_complexity':c['functions'][0]['cyclomatic_complexity'],'resumed_status':resumed.summary['status'],'resumed_units':resumed.summary['resumed_units'],'includes':b['includes']}))
