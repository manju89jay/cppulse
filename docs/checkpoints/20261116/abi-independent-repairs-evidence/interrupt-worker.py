from pathlib import Path
import os,sys
import cppulse.abi as abi
original=abi.subprocess.Popen
def spawn(*args,**kwargs):
    process=original(*args,**kwargs)
    Path(sys.argv[1]).write_text(str(process.pid))
    return process
abi.subprocess.Popen=spawn
abi._capture(['/usr/bin/sleep','30'],dict(os.environ),Path('/tmp'),30,1024)
