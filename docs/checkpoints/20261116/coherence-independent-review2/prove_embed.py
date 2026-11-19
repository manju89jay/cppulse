"""Observe unreported #embed input changing actual Clang semantics."""
from pathlib import Path
import hashlib,json,os,subprocess
root=Path('/workspace/cppulse')
out=root/'work/coherence-review2/embed-semantics';out.mkdir()
source=out/'main.cpp'
source.write_text('constexpr unsigned char data[] = {\n#embed "payload.bin"\n};\nstatic_assert(data[0] == 1, "embedded bytes changed");\nint main(){return sizeof(data);}\n')
database=[{'directory':str(out),'file':str(source),'arguments':['clang++','-std=c++23','-c',str(source)]}]
(out/'compile_commands.json').write_text(json.dumps(database,indent=2)+'\n')
binary=root/'work/native-include-buffer-candidate/9004df27f73a73901e3c231834628c24009ffded1730e598754acd6e7c7a6373/cppulse-analyzer'
rows=[]
for label,value in [('one',1),('two',2)]:
 (out/'payload.bin').write_bytes(bytes([value]))
 target=out/label
 argv=[str(binary),'--repo',str(out),'--compilation-database',str(out),'--resource-dir',str(root/'work/native-deps/usr/lib/llvm-19/lib/clang/19'),'--output',str(target)]
 result=subprocess.run(argv,capture_output=True,text=True,timeout=30,env={**os.environ,'LD_LIBRARY_PATH':str(root/'work/native-deps/usr/lib/x86_64-linux-gnu')})
 (out/(label+'-execution.json')).write_text(json.dumps({'argv':argv,'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr},indent=2)+'\n')
 report=json.loads((target/'findings.json').read_text());analysis=report['metadata']['analysis'];native=analysis['native_metrics']['files'][0]
 rows.append({'label':label,'payload_hex':bytes([value]).hex(),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'native_binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'report_sha256':hashlib.sha256((target/'findings.json').read_bytes()).hexdigest(),'status':analysis['files'][0]['status'],'error_count':analysis['files'][0]['error_count'],'includes':native['includes'],'source_content_sha256':native['source_content_sha256']})
assert rows[0]['source_sha256']==rows[1]['source_sha256']
assert rows[0]['source_content_sha256']==rows[1]['source_content_sha256']
assert rows[0]['error_count']==0 and rows[1]['error_count']>0, rows
assert all(row['includes']==[] for row in rows)
(out/'verification.json').write_text(json.dumps({'passed':True,'qualification':'Actual Clang19 same source, different undeclared embedded bytes; no inclusion callback edges. Does not claim actual collector normalization execution. Independent red pure normalizer check retained separately.','cases':rows},indent=2)+'\n')
print(json.dumps(rows,indent=2))
