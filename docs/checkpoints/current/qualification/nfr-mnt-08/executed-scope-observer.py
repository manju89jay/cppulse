"""Verify actual repository decision authority, exact preservation and scope."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

root = Path(__file__).resolve().parent.parent / 'checkout'
out = Path(sys.argv[1])
source = '4cf0194a3313412511a688e5924f7bb28939d94d'
parent = 'd1e598028aec76f6455a7ed45602945274b72f8d'
main = '82120d26b51f99b64068f9d66f6e000fcaee97c2'
definition = 'e57e89fb7db188f1f4805b95c0bc6f2896c7ab9eef15d851723cc422a0bd2381'


def git(*args, checkout=root):
    return subprocess.check_output(['git', *args], cwd=checkout)


def digest(body):
    return hashlib.sha256(body).hexdigest()


declared = [
    'TASK_SPEC.md', 'docs/specs/production-platform/requirements.md',
    'docs/specs/production-platform/tasks.md', 'docs/specs/production-platform/design.md',
    'docs/plans/cppulse-production-completion-plan.md', 'docs/plans/production-delivery-ledger.json',
    'docs/plans/production-completion-traceability.json', 'scripts/verify_delivery.py',
]
stable = {}
assert git('write-tree').decode().strip() == source
for name in declared:
    body = (root / name).read_bytes()
    assert body == git('show', parent + ':' + name)
    stable[name] = digest(body)
ledger = json.loads((root / declared[5]).read_bytes())
rows = ledger['items']
counts = Counter(row['state'] for row in rows)
assert counts == {'verified': 38, 'open': 96, 'active': 51, 'blocked': 2}
assert len(rows) == len({row['id'] for row in rows}) == 187
assert {p['id'] for p in ledger['phases']} == {f'P{i}' for i in range(15)}
assert definition.encode() in (root / declared[5]).read_bytes()

decision = root / 'docs/DECISIONS.md'
authority_path = root / 'docs/plans/production-scope-authority.md'
decisions, authority = decision.read_bytes(), authority_path.read_text()
old = git('show', parent + ':docs/DECISIONS.md')
assert decisions.startswith(old)
pattern = re.compile(r'^## ((?:D\d+)|(?:PROD-\d{8}-\d+))\b', re.M)
current = [m[1] for m in pattern.finditer(decisions.decode())]
previous = [m[1] for m in pattern.finditer(old.decode())]
index = re.findall(r'(?:\|\s|`)((?:D\d+)|(?:PROD-\d{8}-\d+))(?:\s\||`)', authority)
assert len(set(current)) == len(current) == 99 and index == current
assert current[:len(previous)] == previous and len(previous) == 95
new = decisions.decode().split('## PROD-20261121-32', 1)[1]
for field in ('Context', 'Decision', 'Why', 'Tradeoffs', 'Interview angle'):
    assert f'**{field}**.' in new

for text in ('historical six-component MVP', '“Proposed” headers', 'C++ is the first',
             'formatting source of truth', 'preserve meaningful failures',
             'one heavyweight job', '4 GiB disk reserve', 'one independent read-only batch reviewer',
             'exit 2 is an invalid or stale', 'Exit 3 means valid evidence',
             'Full-program completion requires exit 0',
             'The object and reference observations in batch111 apply to its originating',
             'remaining M0-01 history requirements open'):
    assert text.casefold() in authority.casefold(), text
assert 'CMAKE_CXX_STANDARD 17' in (root / 'analyzer-core/CMakeLists.txt').read_text()
clang_style = (root / '.clang-format').read_text()
for text in ('BasedOnStyle: Google', 'IndentWidth: 4', 'ColumnLimit: 100'):
    assert text in clang_style
assert git('cat-file', '-t', main).decode().strip() == 'commit'
ref = 'refs/remotes/origin/feat/health-score-v2'
isolated = subprocess.run(['git', 'show-ref', '--verify', '--quiet', ref], cwd=root)
receiving = subprocess.run(['git', 'show-ref', '--verify', '--quiet', ref], cwd='/workspace/cppulse')
assert isolated.returncode == 1 and receiving.returncode == 0
status = {}
for label, command in (
    ('plan', [sys.executable, '-B', 'docs/plans/verify_production_plan.py']),
    ('strict', [sys.executable, '-B', 'scripts/verify_delivery.py', '--require-complete',
                '--output', str(out/'strict.json')]),
):
    run = subprocess.run(command, cwd=root, capture_output=True)
    (out/(label+'.stdout')).write_bytes(run.stdout)
    (out/(label+'.stderr')).write_bytes(run.stderr)
    status[label] = run.returncode
assert status == {'plan': 0, 'strict': 2}
assert b'current38-source-proof.json' in (out/'strict.stdout').read_bytes()
(out/'governance.json').write_text(json.dumps({
    'source_tree': source, 'head': git('rev-parse', 'HEAD').decode().strip(),
    'preserved_first_parent_files': stable, 'first_parent_decision_bytes': len(old),
    'first_parent_decision_sha256': digest(old), 'decision_index_order': current,
    'definition_sha256_recorded_in_exact_ledger': definition,
    'states': dict(counts), 'phase_count': 15, 'current_local_second_parent': main,
    'isolated_matching_ref_exit': isolated.returncode,
    'receiving_matching_ref_exit': receiving.returncode,
    'actual_commands': status,
    'scope': 'Governance and wording checks only. Actual public strict verification remains invalid.'
}, indent=2) + '\n')
print('Actual governance checklist completed and the plan check passed. Actual strict verification exited 2.')
