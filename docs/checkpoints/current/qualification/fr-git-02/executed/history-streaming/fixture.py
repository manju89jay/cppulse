"""Derive expected Git bytes independently and materialize them only at runtime."""

import base64
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys


LANE = Path(__file__).resolve().parent
GIT = '/usr/bin/git'


def sha(body):
    return hashlib.sha256(body).hexdigest()


def oid(kind, body):
    return hashlib.sha1(f'{kind} {len(body)}\0'.encode() + body, usedforsecurity=False).hexdigest()


def encode(body):
    return base64.b64encode(body).decode()


def declare(spec):
    result = []
    files = {}
    for row in spec['commits']:
        files.update({path: content.encode() for path, content in row['files'].items()})
        files = dict(sorted(files.items()))
        blobs = {name: {'id': oid('blob', body), 'body': encode(body)} for name, body in files.items()}
        tree = b''.join(f'100644 {name}\0'.encode() + bytes.fromhex(blob['id']) for name, blob in blobs.items())
        tree_id = oid('tree', tree)
        previous = result[-1]['id'] if result else None
        parent_header = f'parent {previous}\n' if previous else ''
        name = row['actor']
        email = f'{name.lower()}@example.invalid'
        epoch = int(datetime.fromisoformat(row['date']).timestamp())
        signature = f'{name} <{email}> {epoch} +0000'
        message = row['message'] + 'x' * row.get('message_padding', 0) + '\n'
        body = (f'tree {tree_id}\n{parent_header}author {signature}\ncommitter {signature}\n\n' + message).encode()
        result.append({'label': row['id'], 'id': oid('commit', body), 'body': encode(body), 'size_bytes': len(body),
                       'tree': tree_id, 'tree_body': encode(tree), 'parent': previous,
                       'actor': name, 'email': email, 'date': f'@{epoch} +0000', 'message': message, 'files': blobs})
    return result


def command(root, *args, data=None, env=None):
    argv = [GIT, '-C', str(root), '-c', 'core.hooksPath=/dev/null', *args]
    result = subprocess.run(argv, input=data, env=env, capture_output=True, timeout=30, check=False)
    assert result.returncode == 0, (argv, result.returncode, result.stderr)
    return result.stdout


def materialize(root, objects):
    root.mkdir()
    command(root, 'init', '--quiet', '--initial-branch=main', '--object-format=sha1', '--template=')
    written = set()
    for row in objects:
        for blob in row['files'].values():
            if blob['id'] not in written:
                actual = command(root, 'hash-object', '-w', '-t', 'blob', '--stdin', data=base64.b64decode(blob['body']))
                assert actual.decode().strip() == blob['id']
                written.add(blob['id'])
        tree_input = b''.join(f"100644 blob {blob['id']}\t{name}\0".encode() for name, blob in row['files'].items())
        assert command(root, 'mktree', '-z', data=tree_input).decode().strip() == row['tree']
        environment = dict(os.environ, GIT_AUTHOR_NAME=row['actor'], GIT_AUTHOR_EMAIL=row['email'],
                           GIT_AUTHOR_DATE=row['date'], GIT_COMMITTER_NAME=row['actor'],
                           GIT_COMMITTER_EMAIL=row['email'], GIT_COMMITTER_DATE=row['date'])
        parent = ['-p', row['parent']] if row['parent'] else []
        actual = command(root, 'commit-tree', row['tree'], *parent, '-F', '-',
                         data=row['message'].encode(), env=environment)
        assert actual.decode().strip() == row['id'], (actual, row['id'])
    command(root, 'update-ref', 'refs/heads/main', objects[-1]['id'])
    command(root, 'reset', '--hard', '--quiet', 'refs/heads/main')
    verify(root, objects)


def verify(root, objects):
    assert not command(root, 'remote').strip()
    assert command(root, 'rev-parse', '--is-shallow-repository').strip() == b'false'
    assert command(root, 'show-ref', '--heads', '--tags').decode().splitlines() == [f"{objects[-1]['id']} refs/heads/main"]
    assert command(root, 'rev-list', 'HEAD').decode().splitlines() == [row['id'] for row in reversed(objects)]
    for row in objects:
        assert encode(command(root, 'cat-file', 'commit', row['id'])) == row['body']
        assert encode(command(root, 'cat-file', 'tree', row['tree'])) == row['tree_body']
    for path, blob in objects[-1]['files'].items():
        assert encode((root / path).read_bytes()) == blob['body']
    return {
        path.relative_to(root).as_posix(): {'mode': stat.S_IMODE(path.stat().st_mode), 'sha256': sha(path.read_bytes())}
        for path in sorted(root.rglob('*')) if path.is_file() and not path.is_symlink()
    }


if __name__ == '__main__':
    assert sys.argv[1:] == ['declare-only']
    spec = json.loads((LANE / 'fixture.json').read_bytes())
    with (LANE / 'objects.json').open('x', encoding='utf-8') as stream:
        json.dump(declare(spec), stream, indent=2, allow_nan=False)
        stream.write('\n')
