"""Lazy ordinal index lifetime, identity and finite admission controls."""
from collections.abc import Sequence, Mapping
from pathlib import Path
import weakref

import pytest

from cppulse.errors import ContractError
from cppulse.native_metric_index import MetricRowIndex


class Lazy(Sequence):
    def __init__(self, paths):
        self.paths = paths
        self.accesses = []
        self.last = None

    def __len__(self):
        return len(self.paths)

    def __getitem__(self, i):
        class Row(dict):
            pass

        assert isinstance(i, int)
        if i < 0 or i >= len(self.paths):
            raise IndexError(i)
        assert self.last is None or self.last() is None, "previous row retained"
        self.accesses.append(i)
        row = Row(path=self.paths[i], tokens=[{"payload": i}])
        self.last = weakref.ref(row)
        return row


def test_lazy_order_lookup_no_cache(tmp_path):
    source = Lazy(["/repo/b", "/repo/a"])
    index = MetricRowIndex(source, lambda p: p.removeprefix("/repo/"))
    assert isinstance(index, Mapping) and list(index) == ["b", "a"] and len(index) == 2
    assert source.accesses == [0, 1] and source.last() is None
    assert index["a"]["tokens"] == [{"payload": 1}]
    assert index.get("b")["path"] == "/repo/b"
    assert index["a"]["path"] == "/repo/a"
    assert source.accesses == [0, 1, 1, 0, 1]
    assert index.get("missing") is None
    with pytest.raises(KeyError):
        index["missing"]
    assert source.accesses == [0, 1, 1, 0, 1]


def test_reference_mapping_and_empty():
    rows = [{"path": "a", "tokens": [1]}, {"path": "b", "tokens": [2]}]
    index = MetricRowIndex(rows, lambda x: x)
    assert dict(index) == {row["path"]: row for row in rows}
    assert dict(MetricRowIndex([], lambda x: x)) == {}


@pytest.mark.parametrize("paths", [["/a", "/a"], ["/repo/a", "a"]])
def test_duplicate_aliases(paths):
    with pytest.raises(ContractError):
        MetricRowIndex(Lazy(paths), lambda p: p.removeprefix("/repo/"))


def test_source_identity_drift_and_redecode():
    rows = [{"path": "a", "tokens": [1]}]
    index = MetricRowIndex(rows, lambda x: x)
    rows[0]["tokens"] = [2]
    assert index["a"]["tokens"] == [2]
    rows[0]["path"] = "b"
    with pytest.raises(ContractError):
        index["a"]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_files": True},
        {"max_files": 0},
        {"max_files": 1.0},
        {"max_identity_bytes": False},
        {"max_identity_bytes": 0},
    ],
)
def test_limits_before_source_access(kwargs):
    class Bad(Sequence):
        def __len__(self):
            raise AssertionError("source touched")

        def __getitem__(self, i):
            raise AssertionError("source touched")

    with pytest.raises(ContractError):
        MetricRowIndex(Bad(), lambda x: x, **kwargs)


def test_count_budget_before_element():
    class Bad(Sequence):
        def __len__(self):
            return 2

        def __getitem__(self, i):
            raise AssertionError("element touched")

    with pytest.raises(ContractError):
        MetricRowIndex(Bad(), lambda x: x, max_files=1)


@pytest.mark.parametrize("identity", [lambda x: 1, lambda x: "\ud800", lambda x: "λ"])
def test_identity_type_unicode_bytes(identity):
    with pytest.raises(ContractError):
        MetricRowIndex([{"path": "a"}], identity, max_identity_bytes=1)


def test_actual_utf8_total_boundary():
    rows = [{"path": "λ"}, {"path": "é"}]
    assert list(MetricRowIndex(rows, lambda x: x, max_identity_bytes=4)) == ["λ", "é"]
    with pytest.raises(ContractError):
        MetricRowIndex(rows, lambda x: x, max_identity_bytes=3)


@pytest.mark.parametrize("kind", ["construction", "lookup"])
def test_callback_errors_preserved(kind):
    class Problem(RuntimeError):
        pass

    failing = False

    def identity(x):
        if failing:
            raise Problem("identity failure")
        return x

    if kind == "construction":
        failing = True
        with pytest.raises(Problem):
            MetricRowIndex([{"path": "a"}], identity)
    else:
        index = MetricRowIndex([{"path": "a"}], identity)
        failing = True
        with pytest.raises(Problem):
            index["a"]


def test_generator_not_supported_and_bad_callback():
    with pytest.raises(ContractError):
        MetricRowIndex(iter([{"path": "a"}]), lambda x: x)
    with pytest.raises(ContractError):
        MetricRowIndex([], None)


@pytest.fixture(autouse=True)
def exact_origin():
    import cppulse.native_metric_index as module

    assert (
        Path(module.__file__).resolve()
        == Path(__file__).resolve().parents[1] / "python/cppulse/native_metric_index.py"
    )


@pytest.mark.parametrize("row", [{}, {"path": None}, {"path": 1}, None])
def test_invalid_row_declarations(row):
    with pytest.raises(ContractError):
        MetricRowIndex([row], lambda x: x)


@pytest.mark.parametrize("phase", ["construction", "lookup"])
def test_source_decode_exception_preserved(phase):
    class Problem(RuntimeError):
        pass

    class Source(Sequence):
        failing = phase == "construction"

        def __len__(self):
            return 1

        def __getitem__(self, i):
            if self.failing:
                raise Problem("decode failure")
            return {"path": "a"}

    source = Source()
    if phase == "construction":
        with pytest.raises(Problem):
            MetricRowIndex(source, lambda x: x)
    else:
        index = MetricRowIndex(source, lambda x: x)
        source.failing = True
        with pytest.raises(Problem):
            index["a"]


def test_sequence_growth_during_construction_refuses():
    class Growing(Sequence):
        count = 1

        def __len__(self):
            return self.count

        def __getitem__(self, i):
            self.count = 2
            return {"path": "a"}

    with pytest.raises(ContractError):
        MetricRowIndex(Growing(), lambda x: x)


def test_subclass_and_opaque_empty_identity():
    class Count(int):
        pass

    class Text(str):
        pass

    with pytest.raises(ContractError):
        MetricRowIndex([], lambda x: x, max_files=Count(1))
    with pytest.raises(ContractError):
        MetricRowIndex([{"path": "a"}], lambda x: Text("a"))
    index = MetricRowIndex([{"path": "literal"}], lambda x: "")
    assert list(index) == [""] and index[""]["path"] == "literal"


def test_ascii_cumulative_and_single_identity_limits():
    with pytest.raises(ContractError):
        MetricRowIndex(
            [{"path": "aa"}, {"path": "bb"}], lambda x: x, max_identity_bytes=3
        )
    with pytest.raises(ContractError):
        MetricRowIndex([{"path": "long"}], lambda x: x, max_identity_bytes=1)
