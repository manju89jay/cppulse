"""Independent replay attacks against real retained finite ELF observations."""
from copy import deepcopy
import hashlib,json,os
from pathlib import Path
import pytest
from cppulse.errors import ContractError,IntegrityError
from cppulse.identities import canonical_json_bytes
from cppulse.service_repair import validate_report
BASE=Path(os.environ.get('CPPULSE_SERVICE_REVIEW_ROOT','/workspace/cppulse/work/service-independent-review/sealed-transient-tools-v1/observations'))
@pytest.fixture
def retained(tmp_path):
 request=json.loads((BASE/'request.json').read_bytes());report=json.loads((BASE/'report.json').read_bytes())
 root=tmp_path/'view';root.mkdir()
 for a in report['artifacts']:
  p=root/a['path'];p.parent.mkdir(parents=True,exist_ok=True);os.link(BASE/a['path'],p)
 validate_report(request,report,root)
 return request,deepcopy(report),root

def replace(root,report,path,raw):
 p=root/path;p.unlink();p.write_bytes(raw)
 fact={'path':path,'size_bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
 for i,a in enumerate(report['artifacts']):
  if a['path']==path:report['artifacts'][i]=fact;break
 return fact

def progress(root,report,index):
 replace(root,report,f'progress-{index+1}.json',canonical_json_bytes(report['steps'][index]))

def test_unmodified_retained_positive(retained):
 validate_report(*retained)

def test_wrong_perstream_counts_with_consistent_progress(retained):
 request,report,root=retained;r=report['steps'][0];r['outcome']['stdout_bytes']-=1;r['outcome']['stderr_bytes']+=1;progress(root,report,0)
 with pytest.raises(ContractError,match='Incomplete service observations'):validate_report(request,report,root)

def test_forged_supervisor_reason_cannot_override_original_progress(retained):
 request,report,root=retained;report['steps'][8]['outcome']['reason']='changed actual fact'
 with pytest.raises(ContractError,match='original progress'):validate_report(request,report,root)

@pytest.mark.parametrize('kind',['missing_case','clean_before','after_failed','foreign_service','tool_hash','missing_object','cpu_claim'])
def test_materially_unqualified_pair_rejected(retained,kind):
 request,report,root=retained
 if kind=='tool_hash':report['tools']['compiler']['sha256']='0'*64
 elif kind=='missing_object':report['artifacts']=[a for a in report['artifacts'] if a['path']!='after/selected.o']
 elif kind=='cpu_claim':report['qualification']['cpu_enforced']=True
 elif kind=='after_failed':
  report['steps'][8]['outcome'].update(status='failed',returncode=2);progress(root,report,8)
 else:
  index={'missing_case':8,'clean_before':4,'foreign_service':0}[kind];row=report['steps'][index];path=row['stdout']['path'];value=json.loads((root/path).read_bytes())
  if kind=='missing_case':value['cases'].pop(next(iter(value['cases'])))
  elif kind=='clean_before':
   value['cases']={k:True for k in value['cases']};row['outcome'].update(status='passed',returncode=0)
  else:value[0]['Image']='sha256:'+'f'*64
  raw=canonical_json_bytes(value);row['stdout']=replace(root,report,path,raw);row['outcome']['stdout_bytes']=len(raw);row['outcome']['captured_bytes']=len(raw)+row['stderr']['size_bytes'];progress(root,report,index)
 with pytest.raises((ContractError,IntegrityError)):validate_report(request,report,root)
