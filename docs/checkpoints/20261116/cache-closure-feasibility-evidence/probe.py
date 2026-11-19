"""Actual tiny observed-query controls; no cache qualification is inferred."""
from pathlib import Path
import datetime,hashlib,json,os,resource,subprocess
root=Path('/workspace/cppulse');base=root/'work/cache-closure-observation3';native=root/'work/native-include-buffer-candidate/9004df27f73a73901e3c231834628c24009ffded1730e598754acd6e7c7a6373/cppulse-analyzer';sdk=root/'work/native-deps/usr/lib/llvm-19/lib/clang/19'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def limits():
 resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3));resource.setrlimit(resource.RLIMIT_CPU,(30,30));resource.setrlimit(resource.RLIMIT_FSIZE,(2*1024**2,2*1024**2))
env={'PATH':'/usr/bin:/bin','LD_LIBRARY_PATH':str(root/'work/native-deps/usr/lib/x86_64-linux-gnu'),'LC_ALL':'C','LANG':'C','CPPULSE_CLANG_RESOURCE_DIR':str(sdk)}
records=[]
for kind in ('search-precedence','has-include'):
 case=base/kind;project=case/'project';project.mkdir(parents=True,exist_ok=False)
 high=case/'external-first';low=case/'external-second';high.mkdir();low.mkdir()
 header=high/'config.h' if kind=='search-precedence' else high/'flag.h'
 low_header=low/'config.h';low_header.write_text('#define CPPULSE_FLAG 0\n')
 if kind=='search-precedence':text='#include <config.h>\n#if CPPULSE_FLAG\nint f(int x){if(x)return 1;return 0;}\n#else\nint f(int x){return x;}\n#endif\n'
 else:text=f'#if __has_include("{header}")\nint f(int x){{if(x)return 1;return 0;}}\n#else\nint f(int x){{return x;}}\n#endif\n'
 source=project/'main.cpp';source.write_text(text)
 args=['clang++','-std=c++17','-I'+str(high),'-I'+str(low),'-c',str(source)]
 database=project/'compile_commands.json';database.write_text(json.dumps([{'directory':str(project),'file':str(source),'arguments':args}]))
 before_source,before_low=sha(source),sha(low_header)
 for state in ('absent','present'):
  if state=='present':header.write_text('#define CPPULSE_FLAG 1\n')
  output=case/state;trace=case/(state+'.strace');command=['/usr/bin/strace','-f','-qq','-s','4096','-yy','-e','trace=%file,%process','-o',str(trace),str(native),'--repo',str(project),'--compilation-database',str(database),'--resource-dir',str(sdk),'--output',str(output)]
  started=datetime.datetime.now(datetime.timezone.utc).isoformat()
  result=subprocess.run(command,cwd=project,env=env,preexec_fn=limits,capture_output=True,timeout=60)
  (case/(state+'.stdout')).write_bytes(result.stdout);(case/(state+'.stderr')).write_bytes(result.stderr)
  report=output/'findings.json';raw=json.loads(report.read_bytes());metric=raw['metadata']['analysis']['native_metrics']['files'][0]
  lines=trace.read_text().splitlines();selected=[line for line in lines if str(header) in line]
  records.append({'kind':kind,'state':state,'command':command,'started_utc':started,'exit_status':result.returncode,'source_sha256':sha(source),'low_header_sha256':sha(low_header),'source_and_old_header_unchanged':before_source==sha(source) and before_low==sha(low_header),'report_sha256':sha(report),'trace_sha256':sha(trace),'trace_bytes':trace.stat().st_size,'trace_target_lines':selected,'includes':metric['includes'],'cc':[f['cyclomatic_complexity'] for f in metric['functions']],'native_status':metric['status']})
  assert result.returncode==0 and records[-1]['source_and_old_header_unchanged']
  assert selected,(kind,state,'missing selected syscall evidence')
  assert any('ENOENT' in line for line in selected) if state=='absent' else any('ENOENT' not in line for line in selected)
 absent,present=records[-2:]
 assert absent['cc']==[1] and present['cc']==[2],(kind,absent['cc'],present['cc'])
record={'recorded_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'native_sha256':sha(native),'strace_version':subprocess.check_output(['/usr/bin/strace','--version'],text=True).splitlines()[0],'environment':env,'limits':{'per_process_as_bytes':3*1024**3,'per_process_cpu_seconds':30,'per_file_output_bytes':2*1024**2,'wall_seconds':60},'observations':records,'cache_eligibility':'unknown; no production cache behavior changed','limitations':['File/process traces expose missing path probes but do not prove runtime mmap/library bytes, vDSO/clock/environment/PCH closure.','No completeness or authentication claim follows merely from strace exit0.','Actual parsed buffer identities are retained in native reports independently of trace path results.']}
(base/'verification.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps({'controls':len(records),'trace_bytes':sum(r['trace_bytes'] for r in records),'cc_pairs':[r['cc'] for r in records]}))
