"""Source-first original-corpus hand-count pilots; does not qualify full builds."""
from pathlib import Path
import json,hashlib,os,subprocess,sys
sys.path.insert(0,'scripts');from run_six_corpus import verify_report
root=Path.cwd();native=root/'analyzer-core/build-cloud-final/cppulse-analyzer'
samples=[('grpc','src/core/lib/gpr/string.cc',40,{'cyclomatic_complexity':2,'nesting_depth':1,'parameter_count':1,'function_length':15},'Base1 plus one if; no nesting past1; oneparameter; source extent40..54.'),('protobuf','src/google/protobuf/stubs/common.cc',78,{'cyclomatic_complexity':1,'nesting_depth':0,'parameter_count':1,'function_length':15},'Straight-line VersionString body has no decisions; oneparameter; inclusive78..92.'),('poco','Foundation/src/Environment.cpp',44,{'cyclomatic_complexity':2,'nesting_depth':1,'parameter_count':2,'function_length':7},'Overloaded Environment::get has oneif/else andtwoformalparameters; inclusive44..50.')]
protocol=[]
for project,file,line,expected,why in samples:
 source=root/'work/six-corpus'/project;protocol.append({'project':project,'file':file,'line':line,'expected':expected,'rationale':why,'source_sha256':hashlib.sha256((source/file).read_bytes()).hexdigest()})
p=root/'docs/checkpoints/20261116/native/configured-three-hand-count-protocol.json';p.write_text(json.dumps({'scope':'Three source-first selected original functions. Not randomized accuracy or complete configured corpus acceptance.','samples':protocol},indent=2)+'\n')
results=[]
for row in protocol:
 project=row['project'];source=root/'work/six-corpus'/project;build=root/'work/corpus-configured'/project;out=root/'work/corpus-configured-evidence'/f'{project}-pilot';out.mkdir(parents=True,exist_ok=True);selection=out/'selection.json';selection.write_text(json.dumps([row['file']]))
 cmd=[str(native),'--repo',str(source),'--compilation-database',str(build),'--file-list',str(selection),'--output',str(out/'native'),'--resource-dir',os.environ['CPPULSE_CLANG_RESOURCE_DIR'],'--address-space-bytes','3221225472','--cpu-seconds','60','--file-size-bytes','67108864']
 with (out/'native.log').open('w') as log:run=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,timeout=120)
 result={**row,'command':cmd,'exit_status':run.returncode,'compilation_database_sha256':hashlib.sha256((build/'compile_commands.json').read_bytes()).hexdigest(),'full_production_qualification':False}
 if run.returncode==0:
  raw=out/'native/findings.json';report=json.loads(raw.read_bytes());result['verification']=verify_report(report,source,[row['file']]);result['report_sha256']=hashlib.sha256(raw.read_bytes()).hexdigest();file=report['metadata']['analysis']['native_metrics']['files'][0];matches=[f for f in file['functions'] if f['line']==row['line']];result['observed_functions']=matches;result['checks']={k:len(matches)==1 and matches[0][k]==v for k,v in row['expected'].items()};result['observed_context']=report['metadata']['analysis']['files'][0]
 (out/'manifest.json').write_text(json.dumps(result,indent=2)+'\n');results.append(result)
(root/'docs/checkpoints/20261116/native/configured-three-hand-count-comparison.json').write_text(json.dumps({'native_sha256':hashlib.sha256(native.read_bytes()).hexdigest(),'results':results},indent=2)+'\n')
