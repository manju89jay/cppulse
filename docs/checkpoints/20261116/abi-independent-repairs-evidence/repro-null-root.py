from pathlib import Path
import struct,subprocess,json,hashlib
from cppulse.abi import compare
base=Path('work/repairs-abi-review').resolve()
data=bytearray((base/'valid.so').read_bytes());h=struct.unpack_from('<HHIQQQIHHHHHH',data,16)
secs=[struct.unpack_from('<IIQQQQIIQQ',data,h[5]+i*h[10]) for i in range(h[11])];nh=secs[h[12]];names=data[nh[4]:nh[4]+nh[5]]
for sec in secs:
 if names[sec[0]:names.find(b'\0',sec[0])]==b'.debug_info':
  version=struct.unpack_from('<H',data,sec[4]+4)[0];assert version==5
  data[sec[4]+12:sec[4]+sec[5]]=bytes(sec[5]-12)
bad=base/'null-root.so';bad.write_bytes(data)
p=subprocess.run(['/usr/bin/readelf','--debug-dump=info','--debug-dump=abbrev','--dwarf-check',str(bad)],capture_output=True,text=True,timeout=10)
(base/'null-root-readelf.log').write_text(p.stdout+p.stderr)
r=json.loads((base/'zeroed-fixed-request.json').read_text())
for k in ['old','new']:r['pairs'][0][k]={'path':str(bad),'sha256':hashlib.sha256(data).hexdigest()}
report=compare(r,base/'null-root-result')
print(report['status'],report['results'][0]['status'],report['results'][0]['returncode'])
print('readerwarnings', 'Warning:' in p.stdout+p.stderr,'readererrors','Error:' in p.stdout+p.stderr,'taginlog','DW_TAG_compile_unit' in p.stdout+p.stderr)
