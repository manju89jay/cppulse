from pathlib import Path
import subprocess,sys,os,time,signal,json,hashlib
base=Path('work/repairs-abi-review').resolve()
source=Path('python/cppulse/abi.py')

(base/'interrupt-child.pid').unlink(missing_ok=True)
with (base/'interrupt-final-worker.log').open('wb') as output:
 worker=subprocess.Popen([sys.executable,str(base/'interrupt-worker.py'),str(base/'interrupt-child.pid')],stdout=output,stderr=subprocess.STDOUT)
 child=None
 try:
  for _ in range(50):
   pidfile=base/'interrupt-child.pid'
   if pidfile.exists():child=int(pidfile.read_text());break
   time.sleep(.05)
  assert child is not None,'worker did not spawn fixture process'
  os.kill(worker.pid,signal.SIGINT)
  worker.wait(timeout=5)
  try:os.kill(child,0);alive=True
  except ProcessLookupError:alive=False
  proof={'command':'actual /usr/bin/sleep fixture inside ABI _capture, SIGINT delivered to Python worker only','worker_returncode':worker.returncode,'child_pid':child,'child_remained_after_worker_exit':alive,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'cleanup':'SIGKILL own fixture process group in finally'}
  (base/'interrupt-final-proof.json').write_text(json.dumps(proof,indent=2)+'\n')
  print(json.dumps(proof))
 finally:
  if child:
   try:os.killpg(child,signal.SIGKILL)
   except ProcessLookupError:pass
  if worker.poll() is None:worker.kill();worker.wait(timeout=5)
