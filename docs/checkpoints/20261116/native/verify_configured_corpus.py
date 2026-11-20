"""Bounded actual compilation-database checkpoint; no corpus acceptance claim."""
import hashlib,json,os,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'scripts'))
from run_six_corpus import check_source,verify_report
project=sys.argv[1]
root=Path.cwd(); source=root/'work/six-corpus'/project; build=root/'work/corpus-configured'/project
out=root/'work/corpus-configured-evidence'/(sys.argv[2] if len(sys.argv)>2 else project); out.mkdir(parents=True,exist_ok=True)
lock=json.loads((root/'demo/six-corpus-lock.json').read_text()); pin=next(p for p in lock['projects'] if p['id']==project)
state=check_source(source,pin['revision'],100)
db=build/'compile_commands.json'; rows=json.loads(db.read_text()); selected=sorted({str(Path(row['file']).relative_to(source)) for row in rows if Path(row['file']).is_relative_to(source)})
selection=out/'selection.json'; selection.write_text(json.dumps(selected))
native=root/'analyzer-core/build-cloud-final/cppulse-analyzer'
cmd=[str(native),'--repo',str(source),'--output',str(out/'native'),'--compilation-database',str(db),'--resource-dir',os.environ['CPPULSE_CLANG_RESOURCE_DIR'],'--file-list',str(selection),'--address-space-bytes',str(3*1024**3),'--cpu-seconds','600','--file-size-bytes',str(256*1024**2)]
start=time.monotonic()
with (out/'native.log').open('w') as log: run=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,timeout=900)
manifest={'project':project,'source':state,'command':cmd,'exit_status':run.returncode,'seconds':time.monotonic()-start,'selection':selected,'compilation_database_sha256':hashlib.sha256(db.read_bytes()).hexdigest(),'native_sha256':hashlib.sha256(native.read_bytes()).hexdigest(),'full_production_qualification':False}
if run.returncode==0:
 raw=out/'native/findings.json'; report=json.loads(raw.read_bytes()); manifest['report_sha256']=hashlib.sha256(raw.read_bytes()).hexdigest(); manifest['verification']=verify_report(report,source,selected)
 analysis=report['metadata']['analysis'];manifest['context_status_counts']={status:sum(cell['status']==status for cell in analysis['files']) for status in sorted({cell['status'] for cell in analysis['files']})}
 manifest['remaining']='Actual build/test/context coverage, accuracy and complete corpus acceptance remain separate; missing configurations/partial parse cannot qualify.'
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(manifest,indent=2))
