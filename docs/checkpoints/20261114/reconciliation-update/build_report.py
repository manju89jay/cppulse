"""Archived audit generator from the original scratch layout.

Requires the adjacent reconciliation-update inputs and pre-implementation audit
at their original paths. Read the committed HTML/JSON/CSV directly when those
historical scratch inputs are unavailable. No product source is modified.
"""
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from collections import Counter
import csv
import hashlib
import html
import json
import shutil

HERE=Path(__file__).resolve().parent
REPO=HERE.parent.parent/'cppulse'
ORIGINAL=REPO.parent/'reconciliation-audit-20261114'
DEST=REPO/'docs/checkpoints/20261114/reconciliation-update'
DEST.mkdir(parents=True,exist_ok=True)
CODE='79665c4808a7bbd05e69c70ad0bd10379aa8fef1'
BRANCH='codex/cppulse-local-core-20261114'
COLS=['Requirement','Implemented code','Verification evidence','Status','Remaining work']
req=json.loads((HERE/'requirements-update.json').read_text())
tasks=json.loads((HERE/'tasks-update.json').read_text())
oldreq=json.loads((ORIGINAL/'requirements-matrix.json').read_text())
oldtasks=json.loads((ORIGINAL/'tasks-matrix.json').read_text())
allreq=req['rows']+req['additional_design_environment_obligations']
assert len(req['rows'])==118 and len(allreq)==127 and len(tasks['tasks'])==60
assert {r['id']:r['Requirement'] for r in allreq}=={r['id']:r['Requirement'] for r in oldreq['rows']+oldreq['additional_design_environment_obligations']}
assert {r['id']:r['requirement'] for r in tasks['tasks']}=={r['id']:r['Requirement'] for r in oldtasks}

fresh={}
for name in ['native','python','collection']:
    src=REPO/'review/cloud-handoff-verification-20261114'/name
    target=DEST/'fresh-checks'/name;target.mkdir(parents=True,exist_ok=True)
    for p in src.glob('*'):
        if p.is_file():shutil.copyfile(p,target/p.name)
    fresh[name]=json.loads((src/'check.json').read_text())
assert fresh['native']['status']=='passed' and fresh['python']['status']=='passed'
assert fresh['collection']['exit_code']==2
now=datetime.now(timezone.utc)
summary={'updated_at':now.isoformat(),'updated_at_berlin':now.astimezone(ZoneInfo('Europe/Berlin')).isoformat(),'branch':BRANCH,'implementation_checkpoint':CODE,
 'numbered_requirements':118,'additional_design_obligations':9,'tasks':60,
 'requirement_status_counts':dict(Counter(r['Status'] for r in allreq)),
 'task_status_counts':dict(Counter(r['status'] for r in tasks['tasks'])),
 'whole_tasks_closed':[r['id'] for r in tasks['tasks'] if r['full_task_scope_closed']],
 'new_whole_tasks_closed':tasks['summary']['new_full_scope_closed_tasks'],
 'milestones_complete':[],
 'fresh_checks':{'native':'configure/build/139 CTests passed','selected_python':'453 passed; source stable','full_root_collection':'2,322 collected; four collection errors from three missing runtime modules'},
 'qualification':'Full task statuses are acceptance of whole task scope, not percentage complete. Bounded R1 repairs are verified separately. The complete production specification and final package/platform qualification remain unfinished.'}
req['summary']['implementation_checkpoint']=CODE
req['summary']['current_fresh_verification']=summary['fresh_checks']
tasks['implementation_checkpoint']=CODE
for name,value in [('requirements-update.json',req),('tasks-update.json',tasks),('status-summary.json',summary)]:
    (DEST/name).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')
shutil.copyfile(__file__,DEST/'build_report.py')
shutil.copyfile(HERE.parent/'code-push-verification.json',DEST/'code-push-verification.json')

def flat(value):
    return '\n'.join(flat(x) for x in value) if isinstance(value,list) else json.dumps(value,ensure_ascii=False) if isinstance(value,dict) else str(value or '')

taskrows=[]
for row in tasks['tasks']:
    taskrows.append({'id':row['id'],'Requirement':row['requirement'],'Implemented code':flat(row['source_code'])+'\n\n'+row['progress_since_original'],
      'Verification evidence':flat(row['evidence'])+'\n\n'+row['closure_basis'],
      'Status':row['status'],'Remaining work':row['remaining_work'],
      'specification_reference':row['specification_reference'],'Previous status':row['original_status']})
for name,rows in [('requirements-current.csv',allreq),('tasks-current.csv',taskrows)]:
    with (DEST/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=COLS,lineterminator='\n');w.writeheader()
        for row in rows:w.writerow({k:row['id']+' — '+row[k] if k=='Requirement' else row[k] for k in COLS})

completed=[
 ('Native detector repairs','Already-auto suggestions, logical operator double counting and template threshold handling repaired with retained fail-before/pass-after cases. Current combined native suite:139 passed.'),
 ('Configuration and file limits','Ambiguous/duplicate/invalid config rejected; configurable file-byte budget replaces fixed 500 KiB cap, with explicit skip reasons. Native and Python cases exercised.'),
 ('CLI result semantics','Partial/no-data3, invalid/operational2, failed gate1 and cancellation130; effective config and client capabilities/pins implemented.'),
 ('Ranking and knowledge gaps','Unranked file inventory retains unavailable reasons; insufficient history is displayed explicitly. No fabricated0%LOW for partial files.'),
 ('Actual presentation integration','Fresh R1 utfcpp API/packaged UI/PDF flow passed: seven unranked files, no browser errors, readable 9-page PDF. This does not validate complete upstream analysis.'),
 ('Developer tooling','Local facade/typed checks/benchmark execution and CI wrapper reuse implemented;73 focused tests passed at its recorded source scope. Full release/performance/platform gates remain open.'),
 ('README','Clearer product overview and developer workflows implemented and exercised; it retains preview and full-plan boundaries.'),
 ('Full-scope inventory','Every original118 requirement and60task retained; this is M0-01 documentary closure, not complete production delivery.')]
gaps=[
 ('P3 native metrics','Implemented with139 current native tests passing, but CR-only LOC is wrong and the native-output schema gate is still unrun. Measurement correctness remains partial.'),
 ('P3 Python analysis','Contracts: 69 passed; measured normalization/scorer, duplication and trends are not implemented. Full collection reports missing cppulse.maintenance and cppulse.measurements.'),
 ('P4 configurable controls','New policy 1.2 contracts/evaluators are partial; latest recorded runtime: 35 passed / 1 failed requires inspection. Core policy/gate behavior is freshly tested; domain review remains unavailable.'),
 ('P5 scalability','Native finite selection/resource flags compile and current tests pass. Python work_units, scheduler, checked cache/resume and index are absent. Full collection reports missing cppulse.work_units.'),
 ('VS Code','Compile and16 unit tests passed at recorded source. Actual host remains blocked/unverified; package metadata/docs and rebuilding the VSIX are pending.'),
 ('Qualification and later scope','Docker, other OS/compiler combinations, original six-project corpus, human validation, Git intelligence, MCP/skills and M8/M9 expansions remain open.')]

md='# Current task completion and Codex Cloud resume\n\n'
md+=f'Implementation checkpoint: `{CODE}` on `{BRANCH}`. Implementation is stopped.\n\n'
md+='Fresh verification: **139 native tests and453 selected Python tests passed**. Full root collection still has **four errors** from missing runtime modules; no full-suite or production acceptance is claimed.\n\n'
md+='## Finished and checked implementation slices\n\n'
for title,value in completed:md+='- **'+title+':** '+value+'\n'
md+='\n## Whole backlog tasks\n\n'
md+='Only **M0-01** is closed in its documentary inventory scope. No additional whole backlog task or milestone meets every acceptance condition. These tasks are broader than the individual fixes above.\n\n'
md+='| Status | Tasks |\n|---|---:|\n'+''.join(f'| {key} | {value} |\n' for key,value in summary['task_status_counts'].items())
md+='\n## Resume priorities\n\n'
for title,value in gaps:md+='- **'+title+':** '+value+'\n'
md+='\nRead `docs/CODEX_CLOUD_HANDOFF.md`, the updated HTML audit, all production requirements/design/tasks and the full plan/ledger. Reproduce the red cases, fix causes without weakening tests, and continue the complete scope. No additional Git writes, publication or deployment are authorized by this handover.\n'
(DEST/'task-completion-summary.md').write_text(md)

def h(value):return html.escape(flat(value)).replace('\n','<br>')
def table(rows,kind):
    out=['<div class="table-wrap"><table><thead><tr>'+''.join('<th>'+h(c)+'</th>' for c in COLS)+'</tr></thead><tbody>']
    for row in rows:
        status=row['Status'];text=' '.join(flat(row[c]) for c in COLS)
        out.append('<tr id="'+row['id']+'" data-kind="'+kind+'" data-status="'+status+'">')
        for c in COLS:
            value=h(row[c])
            if c=='Requirement':value='<strong>'+row['id']+'</strong><br>'+value+'<p class="small">'+h(row.get('specification_reference',''))+'</p>'
            if c=='Status':value='<b class="'+status.replace(' ','-')+'">'+value+'</b><p class="small">Original: '+h(row.get('Previous status',''))+'</p>'
            if c=='Verification evidence':value+='<p class="small">'+h(row.get('Current revision verification',row.get('qualification','')))+'</p>'
            if c=='Remaining work' and row.get('Remaining acceptance'):value+='<p>'+h(row['Remaining acceptance'])+'</p>'
            out.append('<td>'+value+'</td>')
        out.append('</tr>')
    return '\n'.join(out+['</tbody></table></div>'])

style='''body{font:15px/1.55 system-ui,sans-serif;color:#172b3a;max-width:1850px;margin:28px auto;padding:0 24px}h1,h2,h3{color:#143e5c;line-height:1.2}h2{margin-top:2em}p,li{max-width:1150px}code{background:#eef2f5;padding:2px 4px;overflow-wrap:anywhere}.notice{background:#fff7e1;border-left:5px solid #b47800;padding:14px}.good{background:#eff8f1;padding:12px}.controls{position:sticky;top:0;background:#fff;padding:12px;border:1px solid #ccd5dd;z-index:1;display:flex;gap:12px;flex-wrap:wrap}input,select{font:inherit;padding:6px}.table-wrap{overflow:auto}table{border-collapse:collapse;width:100%;font-size:12px;margin:18px 0}th,td{border:1px solid #cbd6df;padding:10px;vertical-align:top;text-align:left;overflow-wrap:anywhere}th{background:#143e5c;color:white}th:nth-child(1){width:19%}th:nth-child(2){width:20%}th:nth-child(3){width:27%}th:nth-child(4){width:9%}th:nth-child(5){width:25%}tr:nth-child(even){background:#f4f7fa}.small{font-size:11px;color:#526778}.verified{color:#11603b}.partial{color:#8b5b00}.missing,.conflicting{color:#a62638}.implemented-but-unverified{color:#57438b}a{color:#146295}[hidden]{display:none!important}@media print{.controls{display:none}tbody tr[hidden]{display:table-row!important}.table-wrap[hidden]{display:block!important}tr{display:table-row!important}h2{break-after:avoid}table{font-size:8px}tr{break-inside:avoid}thead{display:table-header-group}.table-wrap{overflow:visible}@page{size:A3 landscape;margin:14mm}}'''
body='<h1>cppulse reconciliation audit — implementation checkpoint update</h1>'
body+='<p>Updated '+h(summary['updated_at_berlin'])+'. Source inspected: <code>'+CODE+'</code> on <code>'+BRANCH+'</code>.</p>'
body+='<div class="notice"><strong>The complete production tool is unfinished. Implementation is paused for handover.</strong><p>Fresh checks passed 139 native tests and453 selected Python tests. Full root collection fails with four missing-module errors. A green subset, contract, scaffold or package build does not close a whole task.</p></div>'
body+='<p>This update preserves all 118 numbered requirements, nine additional design/environment obligations and all 60 M0–M9 tasks. It compares the complete specification, including expansions. M8/M9 were not removed. Counts classify scope; they are not percentage completion.</p>'
body+='<p><a href="https://github.com/manju89jay/cppulse/blob/'+BRANCH+'/docs/CODEX_CLOUD_HANDOFF.md">Codex Cloud handover</a> · <a href="https://github.com/manju89jay/cppulse/tree/'+BRANCH+'">Resume branch</a> · <a href="https://github.com/manju89jay/cppulse/blob/'+BRANCH+'/docs/checkpoints/20261114/reconciliation-update/task-completion-summary.md">Short task summary</a></p>'
body+='<h2>Finished and checked implementation slices</h2><ul>'+''.join('<li><strong>'+h(t)+':</strong> '+h(v)+'</li>' for t,v in completed)+'</ul>'
body+='<h2>What is still unfinished</h2><ul>'+''.join('<li><strong>'+h(t)+':</strong> '+h(v)+'</li>' for t,v in gaps)+'</ul>'
body+='<h2>Whole-task completion</h2><p><strong>M0-01</strong> remains closed in its inventory/provenance scope. No new whole task or milestone is declared complete. The working repairs above are retained; broader acceptance, integration and qualification obligations remain open.</p>'
body+='<p>'+h(summary['task_status_counts'])+'</p><p>Legend: <strong>verified</strong> means the named scope has actual applicable evidence; <strong>implemented but unverified</strong> has implementation without applicable acceptance; <strong>partial</strong> meets only part of the requirement; <strong>missing</strong> has no implementation; <strong>conflicting</strong> contradicts the target. Every status retains limitations and remaining work.</p>'
body+='<h2>Full comparison checklist</h2><p>Filter by task, requirement ID, status or text. Filtering changes the display only, never the stored assessment.</p><div class="controls"><label>Section <select id="section"><option value="task">Tasks (60)</option><option value="requirement">Requirements (118)</option><option value="obligation">Design/environment (9)</option><option value="all">All (187)</option></select></label><label>Status <select id="status"><option value="all">All statuses</option>'+''.join('<option>'+s+'</option>' for s in ['verified','implemented but unverified','partial','missing','conflicting'])+'</select></label><label>Search <input id="query" placeholder="M4, VS Code, coverage…"></label><span id="count"></span></div>'
body+=table(taskrows,'task')+table(req['rows'],'requirement')+table(req['additional_design_environment_obligations'],'obligation')
body+='<h2>Resume contract</h2><p>Read TASK_SPEC first, then AGENTS/CLAUDE and the handover. Retain the full plan. Start with the documented missing modules and CR-only LOC defect, accept native output contracts before dependent consumers, finish current policy/editor/scale tracks, then continue all remaining scope. Use explicit source/artifact-bound evidence and independent review. No false certification, benchmark, accuracy or platform claims. Git writes after this handover require separate authorization.</p>'
body+='<p>Original pre-implementation audit and its historical evidence are preserved under docs/checkpoints/20261114/pre-implementation-audit. The updated machine-readable rows, CSVs and fresh logs are in docs/checkpoints/20261114/reconciliation-update. Some earlier local artifacts were intentionally not committed; their original paths and scope remain disclosed rather than fabricated.</p>'
script='''const rows=[...document.querySelectorAll("tbody tr")];function filter(){const section=document.getElementById("section").value,status=document.getElementById("status").value,q=document.getElementById("query").value.toLowerCase();let n=0;for(const row of rows){const visible=(section==="all"||row.dataset.kind===section)&&(status==="all"||row.dataset.status===status)&&row.textContent.toLowerCase().includes(q);row.hidden=!visible;if(visible)n++;}document.getElementById("count").textContent=n+" rows shown";for(const wrap of document.querySelectorAll(".table-wrap")){wrap.hidden=!wrap.querySelector("tbody tr:not([hidden])");}}for(const id of ["section","status","query"])document.getElementById(id).addEventListener("input",filter);filter();'''
document='<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>cppulse reconciliation and Cloud handover</title><style>'+style+'</style></head><body>'+body+'<script>'+script+'</script></body></html>'
report=REPO/'docs/portfolio/cppulse-reconciliation-audit.html';report.write_text(document)
original_html=ORIGINAL/'cppulse-reconciliation-audit.html'; backup=ORIGINAL/'cppulse-reconciliation-audit.original.html'
if not backup.exists():shutil.copyfile(original_html,backup)
original_html.write_text(document)
shutil.copyfile(report,HERE/'cppulse-reconciliation-audit.html')
shutil.copyfile(DEST/'task-completion-summary.md',HERE/'task-completion-summary.md')
# Descriptive current audit status is distinct from final release acceptance.
ledger_path=REPO/'docs/plans/production-delivery-ledger.json';ledger=json.loads(ledger_path.read_text())
status_by_id={r['id']:r['Status'] for r in allreq}|{r['id']:r['status'] for r in tasks['tasks']}
for row in ledger['items']:
    row['handoff_audit_status']=status_by_id[row['id']]
    row['handoff_audit_reference']='docs/portfolio/cppulse-reconciliation-audit.html#'+row['id']
ledger['handoff_audit_scope']='Current audit labels do not automatically close final release acceptance; original execution state is retained.'
ledger['implementation_checkpoint']=CODE
ledger_path.write_text(json.dumps(ledger,indent=2)+'\n')
print(json.dumps(summary,indent=2))
