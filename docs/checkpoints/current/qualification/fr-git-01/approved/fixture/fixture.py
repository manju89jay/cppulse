"""Declare and verify a real local six-commit Git DAG and its shallow clone."""

import base64
from datetime import datetime
import hashlib
from pathlib import Path
import subprocess


GIT = Path('/usr/bin/git')


def git(repo, *args, data=None, env=None, expected=0):
    command = [str(GIT), '-C', str(repo), '-c', 'core.hooksPath=/dev/null', *args]
    result = subprocess.run(command, input=data, env=env, capture_output=True, timeout=30)
    if result.returncode != expected:
        raise RuntimeError(f'{command}: {result.returncode}: {result.stderr!r}')
    return result.stdout


def oid(kind, body):
    return hashlib.sha1(f'{kind} {len(body)}\0'.encode() + body, usedforsecurity=False).hexdigest()


def encoded(body):
    return base64.b64encode(body).decode()


def declare(spec):
    """Calculate expected Git object identities and bytes independently of Git."""
    result = {}
    for row in spec['commits']:
        parents = [result[name] for name in row['parents']]
        files = dict(parents[0]['files']) if parents else {}
        for path, (symbol, lines) in row.get('add', {}).items():
            content = ''.join(f'int {symbol}_{i} = {i};\n' for i in range(1, lines + 1)).encode()
            files[path] = {'blob': oid('blob', content), 'base64': encoded(content)}
        for before, after in row.get('rename', {}).items():
            files[after] = files.pop(before)
        for path in row.get('remove', []):
            del files[path]
        for path, parent in row.get('from_parent', {}).items():
            files[path] = result[parent]['files'][path]
        files = dict(sorted(files.items()))
        tree = b''.join(f'100644 {path}\0'.encode() + bytes.fromhex(file['blob'])
                        for path, file in files.items())
        tree_id = oid('tree', tree)
        previous = [parent['commit'] for parent in parents]
        header = f'tree {tree_id}\n' + ''.join(f'parent {value}\n' for value in previous)
        epoch = int(datetime.fromisoformat(row['date']).timestamp())
        actor = row['actor']
        email = actor.lower() + '@example.invalid'
        signature = f'{actor} <{email}> {epoch} +0000'
        message = row['subject'] + '\n'
        body = (header + f'author {signature}\ncommitter {signature}\n\n' + message).encode()
        result[row['id']] = {'commit': oid('commit', body), 'tree': tree_id,
                             'parents': previous, 'tree_base64': encoded(tree), 'commit_base64': encoded(body),
                             'actor': actor, 'email': email, 'epoch': epoch, 'message': message, 'files': files}
    return result


def init(repo):
    repo.mkdir()
    git(repo, 'init', '--quiet', '--initial-branch=main', '--object-format=sha1', '--template=')


def materialize(parent, declared, depth):
    import os

    source = parent / 'source'
    init(source)
    for row in declared.values():
        for file in row['files'].values():
            content = base64.b64decode(file['base64'])
            actual = git(source, 'hash-object', '-w', '-t', 'blob', '--stdin', data=content).decode().strip()
            assert actual == file['blob']
        tree = b''.join(f"100644 blob {file['blob']}\t{path}\0".encode()
                        for path, file in row['files'].items())
        actual = git(source, 'mktree', '-z', data=tree).decode().strip()
        assert actual == row['tree']
        actor, email = row['actor'], row['email']
        date = f"@{row['epoch']} +0000"
        signature = dict(os.environ, GIT_AUTHOR_NAME=actor, GIT_AUTHOR_EMAIL=email, GIT_AUTHOR_DATE=date,
                         GIT_COMMITTER_NAME=actor, GIT_COMMITTER_EMAIL=email, GIT_COMMITTER_DATE=date)
        options = [arg for commit in row['parents'] for arg in ('-p', commit)]
        actual = git(source, 'commit-tree', row['tree'], *options, '-F', '-',
                     env=signature, data=row['message'].encode()).decode().strip()
        assert actual == row['commit'], (actual, row['commit'])
    git(source, 'update-ref', 'refs/heads/main', declared['merge']['commit'])
    git(source, 'update-ref', 'refs/heads/side', declared['side']['commit'])
    git(source, 'reset', '--hard', '--quiet', 'refs/heads/main')

    shallow = parent / 'shallow'
    git(parent, '-c', 'protocol.file.allow=always', 'clone', '--quiet', '--no-local', '--no-tags', '--single-branch',
        '--branch', 'main', '--depth', str(depth), '--template=', source.as_uri(), str(shallow))
    git(shallow, 'remote', 'remove', 'origin')
    absent = parent / 'absent'
    absent.mkdir()
    (absent / 'absent.cpp').write_text('int absent = 1;\n')
    unborn = parent / 'unborn'
    init(unborn)
    (unborn / 'unborn.cpp').write_text('int unborn = 1;\n')
    git(unborn, 'add', '--', 'unborn.cpp')
    return inventory(parent, declared)


def file_map(directory):
    return {path.relative_to(directory).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(directory.rglob('*')) if path.is_file() and not path.is_symlink()}


def inventory(parent, declared):
    source = parent / 'source'
    shallow = parent / 'shallow'
    head = declared['merge']['commit']
    assert not git(source, 'remote').strip() and not git(shallow, 'remote').strip()
    assert git(source, 'rev-parse', '--is-shallow-repository').strip() == b'false'
    assert git(shallow, 'rev-parse', '--is-shallow-repository').strip() == b'true'
    assert (shallow / '.git/shallow').read_text().strip() == head
    assert git(shallow, 'rev-list', 'HEAD').decode().splitlines() == [head]
    for id_ in declared['merge']['parents']:
        git(shallow, 'cat-file', '-e', id_, expected=1)
    assert set(git(source, 'rev-list', 'HEAD').decode().splitlines()) == {
        row['commit'] for row in declared.values()
    }
    refs = git(source, 'show-ref', '--heads', '--tags').decode().splitlines()
    assert refs == [f'{head} refs/heads/main', f"{declared['side']['commit']} refs/heads/side"]
    for row in declared.values():
        assert encoded(git(source, 'cat-file', 'commit', row['commit'])) == row['commit_base64']
        assert encoded(git(source, 'cat-file', 'tree', row['tree'])) == row['tree_base64']
        for file in row['files'].values():
            assert encoded(git(source, 'cat-file', 'blob', file['blob'])) == file['base64']
    assert encoded(git(shallow, 'cat-file', 'commit', head)) == declared['merge']['commit_base64']
    rename = git(source, 'diff-tree', '--no-commit-id', '--name-status', '-M', '-r', declared['rename']['commit'])
    deletion = git(source, 'diff-tree', '--no-commit-id', '--name-status', '-r', declared['delete']['commit'])
    assert rename == b'R100\tbefore.cpp\trenamed.cpp\n'
    assert deletion == b'D\tretired.cpp\n'
    assert not (parent / 'absent/.git').exists() and not (parent / 'missing').exists()
    git(parent / 'unborn', 'rev-parse', '--verify', '--quiet', 'HEAD', expected=1)
    return {'head': head, 'refs': refs, 'shallow_boundary': head, 'raw_graph_verified': True,
            'files': {name: file_map(parent / name) for name in ('source', 'shallow', 'absent', 'unborn')}}
