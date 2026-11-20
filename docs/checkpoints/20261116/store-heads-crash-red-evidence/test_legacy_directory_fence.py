"""Executable compatibility-fence design control; not a v3 implementation."""
from pathlib import Path
import pytest
from cppulse.errors import IntegrityError
from cppulse.run_store import RunStore
from test_run_store_v2 import publish


def test_reserved_legacy_paths_refuse_v2_reads_and_head_replacements(tmp_path: Path) -> None:
    store = RunStore(tmp_path / 'store', format_version='2.0.0')
    baseline = publish(store, 'baseline')
    originals = {}
    for name in ('latest.json', 'latest_attempt.json'):
        path = store.root / name
        originals[name] = path.read_bytes()
        path.rename(store.root / (name + '.original'))
        path.mkdir()
    with pytest.raises(IntegrityError):
        store.resolve_latest()
    with pytest.raises(IntegrityError):
        store.resolve_latest_attempt()
    with pytest.raises(IntegrityError):
        publish(store, 'unsupported-v2-writer')
    for name, raw in originals.items():
        assert (store.root / name).is_dir()
        assert (store.root / (name + '.original')).read_bytes() == raw
    assert store.open_run(baseline.run_id).manifest_sha256 == baseline.manifest_sha256
    # Old binary may have renamed this run BEFORE failing head publication.
    assert store.open_run('unsupported-v2-writer').manifest['status'] == 'completed'
