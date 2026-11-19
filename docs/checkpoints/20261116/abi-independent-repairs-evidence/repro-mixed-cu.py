from pathlib import Path
import struct,subprocess,json,hashlib,re
from cppulse.abi import compare
base=Path('work/repairs-abi-review').resolve()
second=base/'second.cpp';second.write_text('struct T { long value; }; extern "C" long second(T* p){return p->value;}\n')
valid=base/'two-cu-valid.so';subprocess.run(['g++','-shared','-fPIC','-g','-Og',str(base/'valid.cpp'),str(second),'-o',str(valid)],check=True)
data=bytearray(valid.read_bytes());h=struct.unpack_from('<HHIQQQIHHHHHH',data,16)
secs=[struct.unpack_from('<IIQQQQIIQQ',data,h[5]+i*h[10]) for i in range(h[11])];nh=secs[h[12]];names=data[nh[4]:nh[4]+nh[5]]
for sec in secs:
 if names[sec[0]:names.find(b'\0',sec[0])]==b'.debug_info':
  offset=sec[4];end=offset+sec[5];units=[]
  while offset<end:
   size=struct.unpack_from('<I',data,offset)[0];assert size and size<0xfffffff0
   units.append((offset,offset+4+size));offset+=4+size
  assert len(units)==2
  begin,end=units[-1];assert struct.unpack_from('<H',data,begin+4)[0]==5
  data[begin+12:end]=bytes(end-begin-12)
bad=base/'mixed-cu-null-root.so';bad.write_bytes(data)
p=subprocess.run(['/usr/bin/readelf','--debug-dump=info','--debug-dump=abbrev','--dwarf-check',str(bad)],capture_output=True,text=True,timeout=10)
(base/'mixed-cu-readelf.log').write_text(p.stdout+p.stderr)
r=json.loads((base/'zeroed-fixed-request.json').read_text())
for k in ['old','new']:r['pairs'][0][k]={'path':str(bad),'sha256':hashlib.sha256(data).hexdigest()}
report=compare(r,base/'mixed-cu-result')
print(report['status'],report['results'][0]['status'],report['results'][0]['returncode'])
print('headers',len(re.findall(r'Compilation Unit @ offset',p.stdout)), 'actual_roots',len(re.findall(r'^ <0><[0-9a-f]+>: Abbrev Number: [1-9][0-9]* \(DW_TAG_compile_unit\)',p.stdout,re.M)),'warnings','Warning:' in p.stdout+p.stderr)
