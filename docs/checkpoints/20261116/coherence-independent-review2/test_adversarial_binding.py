"""Independent synthetic qualification controls; not native execution evidence."""
import hashlib
import pytest
from cppulse.analysis import _include_binding


def binding(*, main=b'int main(){return 0;}\n', header=b'// header\n', arguments=None, identity=True):
    contents = {'main.cpp': main, 'h.hpp': header}
    facts = {path: {'sha256': hashlib.sha256(data).hexdigest(), 'size_bytes': len(data)} for path, data in contents.items()}
    edge = {'target': '/owned/h.hpp'}
    if identity:
        edge['content_identity'] = {'status': 'available', **facts['h.hpp']}
    return _include_binding({'path': '/owned/main.cpp', 'includes': [edge]}, arguments=arguments or [], workspace='/owned', repo='/owned', sources=facts, input_facts=facts, input_links={path:path for path in contents}, read_content=contents.__getitem__)


@pytest.mark.parametrize('kwargs', [
    {'main': b'int x; // __has_inclu\\\nde("missing")\n'},
    {'header': b'const char* d = __DATE__;\n'},
    {'arguments': ['-D', 'QUERY=__has_include("missing")']},
    {'arguments': ['-DQUERY=__has_include("missing")']},
    {'arguments': ['-fmodules-cache-path=/external/cache']},
    {'arguments': ['-Xclang', '-include-pch', '-Xclang', '/external/main.pch']},
    {'identity': False},
])
def test_unsupported_scope_remains_unknown(kwargs):
    assert binding(**kwargs)[0] == 'unverified'


def test_closed_regular_buffers_remain_supported():
    assert binding()[0] == 'matched'


def test_embed_directive_needs_external_input_closure():
    # Paired actual native probe in embed/ shows Clang19 accepts the directive
    # with no includes[] edge. This pure qualification control must fail closed.
    assert binding(main=b'constexpr unsigned char bytes[] = {\n#embed "payload.bin"\n};\n')[0] == 'unverified'


@pytest.mark.parametrize('directive', [b'# embed "payload.bin"', b'%:embed "payload.bin"', b'#/**/embed "payload.bin"', b'#em\\\nbed "payload.bin"', b'#em\\\r\nbed "payload.bin"'])
def test_embed_spelling_controls_remain_unknown(directive):
    assert binding(main=b'unsigned char bytes[] = {\n'+directive+b'\n};\n')[0] == 'unverified'


def test_failed_tu_has_no_verified_buffer_even_with_empty_includes():
    import json
    from pathlib import Path
    native = json.loads(Path('work/coherence-review2/failed-parse/out/findings.json').read_text())['metadata']['analysis']['native_metrics']['files'][0]
    data = b'int main(){return 0;}\n'
    fact = {'sha256':hashlib.sha256(data).hexdigest(),'size_bytes':len(data)}
    status, _, _ = _include_binding(native, arguments=['-std=not-a-standard'], workspace='/workspace/cppulse/work/coherence-review2/failed-parse', repo='/workspace/cppulse/work/coherence-review2/failed-parse', sources={'main.cpp':fact},input_facts={'main.cpp':fact},input_links={'main.cpp':'main.cpp'}, read_content=lambda path:data)
    assert status != 'matched'
