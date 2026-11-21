"""Observe actual installed producer commands and all shared history consumers."""

from contextlib import ExitStack, closing
from copy import deepcopy
from functools import wraps
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys
from unittest.mock import patch

import cppulse
import git
from cppulse.git_miner import behavior, history, history_cache, main, miner, silo_detector, szz_labeler

from fixture import GIT, LANE, declare, materialize, verify


GATES = Path('/workspace/work/git-scope-qualification/gates')
INSTALLED = GATES / 'candidate/installed'
TREE = 'da3f8f074ddbf5a89a9fd6d673f2b39b23b37bbe'
WHEEL = 'db15edf7a6821442ea9b5321ffd3c9ca4d198e704c103cb1f6f044300c034700'
FANOUT = ['miner', 'silos', 'szz', 'metrics-metadata', 'behavior']


def sha(body):
    return hashlib.sha256(body).hexdigest()


def write_json(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def candidate():
    frozen_body = (GATES / 'test-freeze.json').read_bytes()
    artifact = GATES / 'candidate/artifact.json'
    artifact_body = artifact.read_bytes()
    frozen, manifest = json.loads(frozen_body), json.loads(artifact_body)
    for record in (frozen, manifest):
        assert record['candidate_tree'] == TREE and record['wheel_sha256'] == WHEEL
    assert frozen['candidate_manifest'] == str(artifact)
    assert frozen['candidate_manifest_sha256'] == sha(artifact_body)
    assert manifest['installed'] == str(INSTALLED)
    assert sha(Path(manifest['wheel']).read_bytes()) == WHEEL
    return {'tree': TREE, 'wheel_sha256': WHEEL, 'candidate_manifest_sha256': sha(artifact_body),
            'test_freeze_sha256': sha(frozen_body)}


def audit_database(cache):
    database = cache / 'history-v1.sqlite3'
    uri = database.resolve().as_uri() + '?mode=ro&immutable=1'
    rows = {}
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        for commit_id, payload, digest in connection.execute('SELECT commit_id,payload,sha256 FROM raw_records ORDER BY commit_id'):
            record = json.loads(payload)
            assert sha(payload) == digest and record['commit_id'] == commit_id
            rows[commit_id] = {'available': record['available'], 'total_files': record['total_files'],
                               'size_bytes': len(payload), 'sha256': digest, 'limitations': record['limitations']}
    return {'database_sha256': sha(database.read_bytes()), 'raw_records': rows}


def record_case(root, out, case, cache, cutoff, options):
    destination = out / case
    assert not destination.exists()
    real_scan, real_process = main.scan_history, history_cache.run_bounded_process
    scans, fanout, commands, fallbacks = [], [], [], []

    def record_scan(repository, **kwargs):
        assert not scans and Path(repository.working_tree_dir) == root
        result = real_scan(repository, **kwargs)
        assert isinstance(result, history.HistoryScan)
        assert isinstance(result.commits, history_cache.CommitSequence)
        assert isinstance(result.changes, history_cache.ChangeSequence)
        assert result._cache_owner is result.commits.owner is result.changes.owner
        scans.append(result)
        return result

    def forbidden(*args, **kwargs):
        fallbacks.append('full traversal fallback')
        raise AssertionError('A metric or metadata consumer attempted independent full history traversal')

    def observe(name, callable_, *, positional=False):
        @wraps(callable_)
        def wrapped(*args, **kwargs):
            selected = args[0] if positional else kwargs.get('history')
            assert scans and selected is scans[0], name
            fanout.append(name)
            return callable_(*args, **kwargs)

        return wrapped

    def trace_process(argv, **kwargs):
        outcome = real_process(argv, **kwargs)
        operations = [operation for operation in ('rev-list', 'diff-tree', 'blame') if operation in argv]
        assert len(operations) <= 1, argv
        if operations:
            assert argv[0] == GIT and Path(kwargs['cwd']) == root
            commands.append({'operation': operations[0], 'argv': argv, 'status': outcome.status,
                             'exit': outcome.returncode, 'stdout_bytes': outcome.stdout_bytes})
        return outcome

    document = {'cache_dir': str(cache), **options}
    invocation = {'repo': str(root), 'output': str(destination), 'szz_max_fix_commits': 1,
                  'behavior_config': str(LANE / 'behavior.json'), 'behavior_cutoff': cutoff,
                  'history_options': document, 'szz_cutoff': cutoff}
    write_json(out / f'{case}-request.json', invocation)
    with ExitStack() as stack:
        stack.enter_context(patch.object(main, 'scan_history', record_scan))
        stack.enter_context(patch.object(git.Repo, 'iter_commits', forbidden))
        for module in (history, miner, silo_detector, szz_labeler):
            stack.enter_context(patch.object(module, 'scan_history', forbidden))
        stack.enter_context(patch.object(history_cache, 'run_bounded_process', trace_process))
        stack.enter_context(patch.object(miner.GitMiner, 'mine', observe('miner', miner.GitMiner.mine)))
        stack.enter_context(patch.object(silo_detector.SiloDetector, 'detect', observe('silos', silo_detector.SiloDetector.detect)))
        stack.enter_context(patch.object(szz_labeler.SZZLabeler, 'label', observe('szz', szz_labeler.SZZLabeler.label)))
        stack.enter_context(patch.object(main, 'build_output', observe('metrics-metadata', main.build_output)))
        stack.enter_context(patch.object(behavior, 'records_from_scan', observe('behavior', behavior.records_from_scan, positional=True)))
        status = main.run(root, destination, 1, behavior_config=LANE / 'behavior.json',
                          behavior_cutoff=cutoff, history_options=document, szz_cutoff=cutoff)
    write_json(out / f'{case}-fanout.json', {'exit': status, 'observed_shared_scans': len(scans),
                                             'consumers': fanout, 'fallbacks': fallbacks, 'git_commands': commands,
                                             'outputs_retained': sorted(p.name for p in destination.iterdir()) if destination.is_dir() else []})
    assert status == 0 and len(scans) == 1 and fanout == FANOUT and not fallbacks, (case, status, fanout, fallbacks)
    assert all(command['status'] == 'passed' and command['exit'] == 0 for command in commands)
    raw = {name: (destination / f'git_{name}.json').read_bytes() for name in ('history', 'metrics', 'behavior')}
    reports = {name: json.loads(body) for name, body in raw.items()}
    assert reports['history']['selection'] == scans[0].cache_info['selection']
    assert reports['history']['selected_records_complete'] is scans[0].cache_info['selected_records_complete']
    scans[0]._cache_owner.close()
    return {'commands': commands, 'database': audit_database(cache), 'reports': reports,
            'raw_sha256': {name: sha(body) for name, body in raw.items()}}


def check_case(name, result, ids, oversized, blame_parent):
    reports = result['reports']
    raw, legacy, coupling = reports['history'], reports['metrics'], reports['behavior']
    commands = result['commands']
    revisions = [row['argv'] for row in commands if row['operation'] == 'rev-list']
    diffs = [row['argv'] for row in commands if row['operation'] == 'diff-tree']
    blames = [row['argv'] for row in commands if row['operation'] == 'blame']
    expected = {
        'cold': (1, 9, 9, 0, 9, True, False),
        'warm': (0, 0, 0, 9, 9, True, False),
        'fresh': (1, 9, 9, 0, 9, True, False),
        'traversal-bound': (1, 2, 2, 0, 2, True, True),
        'record-bound': (1, 8, 9, 0, 9, False, False),
    }
    actual = (len(revisions), len(diffs), raw['records_extracted'], raw['records_reused'],
              raw['selection']['count'], raw['selected_records_complete'], raw['history_truncated'])
    assert actual == expected[name], (name, actual)
    assert raw['revision_traversals'] == len(revisions) and raw['head'] == ids[0]
    assert raw['mode'] == ('warm' if name == 'warm' else 'cold')
    selected = ids[:2] if name == 'traversal-bound' else ids
    assert raw['selection']['ids_sha256'] == sha(''.join(value + '\n' for value in selected).encode())
    extracted = [] if name == 'warm' else [value for value in selected if name != 'record-bound' or value != oversized]
    assert [next(arg.split('=', 1)[1] for arg in argv if arg.startswith('--attr-source=')) for argv in diffs] == extracted
    if revisions:
        assert revisions[0][-1] == ids[0] and '--max-count=' + ('3' if name == 'traversal-bound' else '101') in revisions[0]
    assert len(blames) == 1 and blames[0][-3:] == [blame_parent, '--', 'a.cpp'], blames
    assert '--porcelain' in blames[0]
    assert legacy['metadata']['szz']['max_fix_commits'] == 1
    assert legacy['metadata']['szz']['analysis_cutoff'] == '2026-11-10T00:00:00Z'
    assert legacy['metadata']['szz']['unavailable_origin_commits'] == 0
    assert ('SZZ analysis capped at 1 most recent bug-fix commits.' in legacy['metadata']['limitations']) is (name != 'traversal-bound')
    file_rows = {row['file']: row for row in legacy['file_metrics']}
    assert file_rows['a.cpp']['szz_bug_introductions'] == 2
    assert file_rows['a.cpp']['bug_fix_commits'] == (1 if name == 'traversal-bound' else 2)
    count = 2 if name == 'traversal-bound' else 3
    assert coupling['counts'] == {'observed_commits': count, 'accepted_commits': count,
                                  'excluded_commits': {}, 'dropped_pair_updates': 0}
    assert coupling['history_status'] == 'partial' and coupling['configuration']['max_commits'] == 3
    assert any('Shared commit stream truncated at the configured max_commits' in note for note in coupling['limitations']) is (name != 'traversal-bound')
    if name == 'traversal-bound':
        for doc in (raw, coupling, legacy['metadata']):
            assert any('History traversal truncated at configured max_commits=2' in note for note in doc['limitations'])
        assert legacy['metadata']['history_status'] == 'partial' and legacy['metadata']['total_commits'] == 2
        assert coupling['coupling'] == []
    else:
        pair, = coupling['coupling']
        assert (pair['left'], pair['right'], pair['support'], pair['left_touches'], pair['right_touches']) == ('a.cpp', 'b.cpp', 2, 3, 2)
        assert any(silo['file'] == 'solo.hpp' and silo['sole_contributor'] == 'Ada' for silo in legacy['knowledge_silos'])
        assert (file_rows['a.cpp']['change_frequency'], file_rows['a.cpp']['lines_added_total'],
                file_rows['a.cpp']['lines_removed_total']) == (8, 9, 7)
    rows = result['database']['raw_records']
    assert set(rows) == set(selected)
    if name == 'record-bound':
        unavailable = [value for value in rows if not rows[value]['available']]
        assert raw['bounds']['max_record_bytes'] == 1024 and unavailable == [oversized]
        assert all(row['size_bytes'] <= 1024 for row in rows.values())
        for doc in (raw, coupling, legacy['metadata']):
            assert any(f'History delta unavailable for {oversized[:8]}' in note and 'max_record_bytes' in note for note in doc['limitations'])
        assert file_rows['record-only.cpp']['change_frequency'] == 0
    else:
        assert all(row['available'] for row in rows.values())
    return {'revision_traversals': actual[0], 'diffs': actual[1], 'extracted': actual[2], 'reused': actual[3],
            'selected': actual[4], 'valid_raw_records': sum(row['available'] for row in rows.values()),
            'selected_records_complete': actual[5], 'truncated': actual[6], 'parent_blame_count': len(blames)}


def stable_metrics(value):
    copy = deepcopy(value)
    del copy['metadata']['analyzed_at']
    return copy


def main_run():
    out = Path(sys.argv[1]).resolve(strict=True)
    assert Path.cwd() == out / 'outside' and Path.home() == Path('/home/agent')
    assert not list(Path.home().iterdir()) and shutil.which('git') == GIT
    for module in (cppulse, behavior, history, history_cache, main, miner, silo_detector, szz_labeler):
        assert Path(module.__file__).resolve().is_relative_to(INSTALLED / 'cppulse'), module.__file__
    receipt = candidate()
    specification = json.loads((LANE / 'fixture.json').read_bytes())
    objects = json.loads((LANE / 'objects.json').read_bytes())
    assert len(objects) == 9 and declare(specification) == objects
    labels = {row['label']: row for row in objects}
    oversized = labels[specification['oversized_commit']]
    assert [row for row in objects if row['size_bytes'] > 1024] == [oversized]
    blame_parent = labels[specification['expected_fix_parent']]['id']
    assert labels[specification['expected_fix']]['parent'] == blame_parent
    root = out / 'repository'
    materialize(root, objects)
    before = verify(root, objects)
    write_json(out / 'repository-before.json', before)

    cases = {
        'cold': ('shared-cache', {}),
        'warm': ('shared-cache', {}),
        'fresh': ('fresh-cache', {}),
        'traversal-bound': ('truncated-cache', {'max_commits': 2}),
        'record-bound': ('record-cache', {'max_record_bytes': 1024}),
    }
    ids = [row['id'] for row in reversed(objects)]
    results, observed = {}, {}
    for name, (cache, overrides) in cases.items():
        if name == 'record-bound':
            baseline = results['cold']
            for equivalent in ('warm', 'fresh'):
                result = results[equivalent]
                assert stable_metrics(result['reports']['metrics']) == stable_metrics(baseline['reports']['metrics'])
                assert result['raw_sha256']['behavior'] == baseline['raw_sha256']['behavior']
                for key in ('head', 'selection', 'checkpoint_sha256', 'profile_digest', 'current_files_digest'):
                    assert result['reports']['history'][key] == baseline['reports']['history'][key], key
            write_json(out / 'first-four-readback.json', {
                'observed_cases': observed, 'metrics_excludes_only': 'metadata.analyzed_at',
                'behavior_byte_identical': True, 'record_bound_pending': True,
            })
        result = record_case(root, out, name, out / cache, specification['cutoff'], {'max_commits': 100, **overrides})
        write_json(out / f'{name}-raw-cache.json', result['database'])
        observed[name] = check_case(name, result, ids, oversized['id'], blame_parent)
        results[name] = result
    after = verify(root, objects)
    write_json(out / 'repository-after.json', after)
    assert after == before and candidate() == receipt
    write_json(out / 'qualification.json', {
        'criterion': 'FR-GIT-02', 'fixture': 'fresh deterministic nine-commit actual Git repository',
        'candidate': receipt, 'commit_ids': ids, 'oversized_commit': {'id': oversized['id'], 'bytes': oversized['size_bytes']},
        'blame_parent': blame_parent, 'producer_cases': observed, 'repository_stable': True,
        'output_sha256': {name: value['raw_sha256'] for name, value in results.items()},
        'equality': {'metrics_excludes_only': 'metadata.analyzed_at', 'behavior_byte_identical': True},
        'limits': ['Finite selected fixture with explicit raw, behavioral, record-size and SZZ caps.',
                   'Candidate SZZ labels and co-change remain scoped historical proxies.'],
    })
    print('FR-GIT-02 recorded five actual installed shared-stream cases')


if __name__ == '__main__':
    main_run()
