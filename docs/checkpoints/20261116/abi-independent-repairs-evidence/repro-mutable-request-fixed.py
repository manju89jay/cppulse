from pathlib import Path
import json,hashlib
import cppulse.abi as abi
base=Path('work/repairs-abi-review').resolve()
r=json.loads((base/'zeroed-fixed-request.json').read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for key in ['old','new']:r['pairs'][0][key]={'path':str(base/'valid.so'),'sha256':sha(base/'valid.so')}
original_tool=Path(r['tool']['path'])
alternate=base/'alternate-fixed-abidiff';alternate.write_bytes(original_tool.read_bytes()+b'caller-selection-mutation-fixture');alternate.chmod(0o500)
original_capture=abi._capture
calls=0
def capture(*args,**kwargs):
 global calls
 outcome=original_capture(*args,**kwargs)
 calls+=1
 if calls==1:r['tool'].update(path=str(alternate),sha256=sha(alternate))
 return outcome
abi._capture=capture
out=base/'mutation-fixed-result'
report=abi.compare(r,out)
proof={'qualification':'Explicit callback injection of caller-owned request mutation, not a real spontaneous concurrent event','source_sha256':sha(Path('python/cppulse/abi.py')),'report_tool_sha256':report['tool']['sha256'],'executed_staged_tool_sha256':sha(out/'inputs/abidiff'),'wrong_tool_identity_published':report['tool']['sha256']!=sha(out/'inputs/abidiff'),'status':report['status']}
(base/'mutation-fixed-proof.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps(proof))
