"""Publication boundary controls; real Docker producer/schema checks are separate."""
from __future__ import annotations
import errno
import os
from pathlib import Path
import sys

import pytest

from cppulse.errors import ContractError, IntegrityError
from test_predictor_input_projection import original


@pytest.fixture
def publisher(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Keep the real original-input guard, isolate only expensive generation."""
    import cppulse.predictor.main as current
    source = tmp_path / "input"
    source.mkdir()
    original(source)

    def generated(input_dir, output_dir, *args, **kwargs):
        output_dir.mkdir(parents=True)
        (output_dir / "risk_scores.json").write_bytes(b"new validated risk fixture")
        (output_dir / "roadmap.json").write_bytes(b"new validated roadmap fixture")

    monkeypatch.setattr(current, "_run_projected", generated)
    return current, source, generated


def test_actual_tmpfs_mount_output_does_not_require_writable_parent_or_cross_devices(publisher) -> None:
    """A genuine mounted destination; no st_dev mock or replacement fallback."""
    if sys.platform != "linux":
        pytest.skip("Linux tmpfs mount boundary; other platform qualification is separate")
    current, source, _ = publisher
    # The managed sandbox sometimes mounts all /dev as one tmpfs rather than
    # /dev/shm separately. Select its actual writable mountpoint, not a mock.
    choices = [Path('/dev/shm'), Path('/dev')]
    target = next((p for p in choices if p.is_dir() and p.stat().st_dev != p.parent.stat().st_dev
                   and os.access(p, os.W_OK)), None)
    assert target is not None, "A real writable tmpfs mount boundary is required for this gate"
    names=[target/'risk_scores.json',target/'roadmap.json']
    assert not any(p.exists() or p.is_symlink() for p in names), "Owned test namespace already has publication leaves"
    try:
        current.run(source,target)
        assert names[0].read_bytes()==b'new validated risk fixture'
        assert names[1].read_bytes()==b'new validated roadmap fixture'
    finally:
        for p in names:
            if p.is_file() and not p.is_symlink():p.unlink()


def test_nonexistent_destination_and_owned_stage_cleanup(publisher,tmp_path:Path) -> None:
    current,source,_=publisher;target=tmp_path/'new'/'output'
    current.run(source,target)
    assert (target/'risk_scores.json').read_bytes()==b'new validated risk fixture'
    assert not list(target.glob('.cppulse-predictor-*'))


@pytest.mark.parametrize('failure',['schema','late-input'])
def test_generation_or_original_guard_failure_leaves_both_existing_outputs(publisher,tmp_path:Path,monkeypatch:pytest.MonkeyPatch,failure:str) -> None:
    current,source,generated=publisher;target=tmp_path/'out';target.mkdir()
    for name in ['risk_scores.json','roadmap.json']:(target/name).write_bytes(b'old')
    kept=target/'caller-owned';kept.mkdir();(kept/'keep').write_text('keep')
    def fail(*args,**kwargs):
        generated(*args,**kwargs)
        if failure=='schema':raise ContractError('Declared second-output schema failure fixture')
        p=source/'findings.json';p.write_bytes(p.read_bytes()+b' ')
    monkeypatch.setattr(current,'_run_projected',fail)
    with pytest.raises((ContractError,IntegrityError)):current.run(source,target)
    assert all((target/n).read_bytes()==b'old' for n in ['risk_scores.json','roadmap.json'])
    assert (kept/'keep').read_text()=='keep' and not list(target.glob('.cppulse-predictor-*'))


@pytest.mark.parametrize('kind',['directory-symlink','leaf-symlink','leaf-fifo'])
def test_unsafe_output_boundary_is_refused_without_touching_existing_target(publisher,tmp_path:Path,kind:str) -> None:
    current,source,_=publisher;target=tmp_path/'out';elsewhere=tmp_path/'elsewhere';elsewhere.mkdir();marker=elsewhere/'old';marker.write_bytes(b'keep')
    if kind=='directory-symlink':target.symlink_to(elsewhere,target_is_directory=True)
    else:
        target.mkdir()
        if kind=='leaf-symlink':(target/'risk_scores.json').symlink_to(marker)
        else:os.mkfifo(target/'roadmap.json')
    try:
        with pytest.raises((IntegrityError,ContractError)):current.run(source,target)
        assert marker.read_bytes()==b'keep'
    finally:
        fifo=target/'roadmap.json'
        if kind=='leaf-fifo' and fifo.exists():fifo.unlink()


def test_second_replace_failure_raises_and_does_not_claim_pair_transaction(publisher,tmp_path:Path,monkeypatch:pytest.MonkeyPatch) -> None:
    current,source,_=publisher;target=tmp_path/'out';target.mkdir()
    for name in ['risk_scores.json','roadmap.json']:(target/name).write_bytes(b'old')
    real=os.replace;calls=[]
    def replace(src,dst,*args,**kwargs):
        calls.append(str(dst))
        if len(calls)==2:raise OSError(errno.EIO,'Declared second publication failure')
        return real(src,dst,*args,**kwargs)
    monkeypatch.setattr(os,'replace',replace)
    with pytest.raises(OSError,match='second publication'):current.run(source,target)
    assert (target/'risk_scores.json').read_bytes()==b'new validated risk fixture'
    assert (target/'roadmap.json').read_bytes()==b'old'
    assert not list(target.glob('.cppulse-predictor-*'))
