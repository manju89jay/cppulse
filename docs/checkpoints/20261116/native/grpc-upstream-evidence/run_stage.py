from __future__ import annotations
import hashlib,json,os,pathlib,resource,signal,subprocess,sys,time
root=pathlib.Path('/workspace/cppulse')
out=root/'work/grpc-upstream-tests-20261116'
stage=sys.argv[1];command=sys.argv[2:]
stage_cwd=pathlib.Path(os.environ.get('CPPULSE_CORPUS_STAGE_CWD',str(root)))
def limits():
    resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))
    resource.setrlimit(resource.RLIMIT_CPU,(600,610))
    resource.setrlimit(resource.RLIMIT_FSIZE,(512*1024**2,512*1024**2))
start=time.monotonic(); before=os.statvfs(root)
with (out/(stage+'.log')).open('wb') as log:
    process=subprocess.Popen(command,cwd=stage_cwd,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,preexec_fn=limits)
    timed_out=False
    try: code=process.wait(timeout=900)
    except subprocess.TimeoutExpired:
        timed_out=True;os.killpg(process.pid,signal.SIGKILL);code=process.wait()
    except BaseException:
        if process.poll() is None:os.killpg(process.pid,signal.SIGKILL)
        process.wait();raise
log=out/(stage+'.log');after=os.statvfs(root)
record={'command':command,'cwd':str(stage_cwd),'driver_sha256':hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),'returncode':code,'timed_out':timed_out,'seconds':time.monotonic()-start,'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest(),'address_space_bytes_per_process':3*1024**3,'cpu_soft_hard_seconds_per_process':[600,610],'file_size_bytes_per_file':512*1024**2,'outer_wall_seconds':900,'free_bytes_before':before.f_bavail*before.f_frsize,'free_bytes_after':after.f_bavail*after.f_frsize,'full_suite_acceptance':False}
(out/(stage+'.json')).write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record));sys.exit(code if code>=0 else 128-code)
