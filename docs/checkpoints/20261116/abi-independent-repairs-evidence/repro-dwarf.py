from pathlib import Path
import subprocess,struct,json,hashlib
from cppulse.abi import compare,_elf_scope
base=Path('work/repairs-abi-review').resolve()
source=base/'valid.cpp';source.write_text('struct S { int x; }; extern "C" int read(S* s) {return s->x;}\n')
valid=base/'valid.so';subprocess.run(['g++','-shared','-fPIC','-g','-Og',str(source),'-o',str(valid)],check=True)
data=bytearray(valid.read_bytes())
h=struct.unpack_from('<HHIQQQIHHHHHH',data,16)
sections=[struct.unpack_from('<IIQQQQIIQQ',data,h[5]+i*h[10]) for i in range(h[11])]
nameh=sections[h[12]];names=data[nameh[4]:nameh[4]+nameh[5]]
for section in sections:
 start=section[0];end=names.find(b'\0',start);name=names[start:end]
 if name in (b'.debug_info',b'.debug_abbrev'):
  data[section[4]:section[4]+section[5]]=bytes(section[5])
bad=base/'zeroed-dwarf.so';bad.write_bytes(data)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
tool=Path('work/abi-tooling/prefix/usr/bin/abidiff').resolve()
r={'version':'1.0.0','tool':{'path':str(tool),'sha256':sha(tool),'version':'2.6.0','library_directory':str(Path('work/abi-tooling/prefix/usr/lib/x86_64-linux-gnu').resolve())},'limits':{'input_bytes':4194304,'wall_seconds':10,'log_bytes':65536},'pairs':[{'id':'invalid-dwarf','old':{'path':str(bad),'sha256':sha(bad)},'new':{'path':str(bad),'sha256':sha(bad)}}]}
report=compare(r,base/'zeroed-result')
(base/'zeroed-request.json').write_text(json.dumps(r,indent=2)+'\n')
print('scope',_elf_scope(data));print(json.dumps(report['results'][0]))
