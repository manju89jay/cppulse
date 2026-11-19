"""Meaningful red: completed publication must expose one coherent head epoch."""
from pathlib import Path
import json
import subprocess
import sys
import time
from cppulse.run_store import RunStore
from test_run_store_v2 import publish


def test_sigkill_between_legacy_pointer_replaces(tmp_path: Path) -> None:
    store = RunStore(tmp_path / 'store', format_version='2.0.0')
    publish(store, 'baseline')
    ready = tmp_path / 'ready'
    program = '''from pathlib import Path
import sys,time
from cppulse.run_store import RunStore
from test_run_store_v2 import publish
original=RunStore._publish_pointer
def barrier(self,snapshot,name):
 original(self,snapshot,name)
 if name=='latest_attempt.json':
  Path(sys.argv[2]).write_text(snapshot.run_id)
  while True:time.sleep(.1)
RunStore._publish_pointer=barrier
publish(RunStore(sys.argv[1],format_version='2.0.0'),'new-completed')
'''
    log = (tmp_path / 'child.log').open('w')
    child = subprocess.Popen([sys.executable,'-c',program,str(store.root),str(ready)],stdout=log,stderr=log)
    try:
        deadline=time.monotonic()+15
        while not ready.exists():
            assert child.poll() is None
            assert time.monotonic()<deadline
            time.sleep(.02)
        child.kill()
        child.wait(timeout=10)
        actual={'latest':store.resolve_latest().run_id,'attempt':store.resolve_latest_attempt().run_id,
                'new_status':store.open_run('new-completed').manifest['status'],'child_returncode':child.returncode}
        (tmp_path / 'observed.json').write_text(json.dumps(actual,indent=2))
        assert actual['new_status']=='completed'
        assert actual['latest']==actual['attempt'], actual
    finally:
        if child.poll() is None:child.kill()
        child.wait(timeout=10)
        log.close()
