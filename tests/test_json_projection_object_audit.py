"""Closed native objects cannot hide discarded fields or present-empty prefixes."""

import hashlib
import io

import pytest

from cppulse.contracts.json_projection import ProjectionComplete, ProjectionSelector
from cppulse.errors import ContractError
from cppulse.json_projection import iter_json_projection


SELECTORS = (
    ProjectionSelector("findings", ("findings",), "array"),
    ProjectionSelector("files", ("metadata", "analysis", "files"), "array", False),
)


def project(data, observer=None, selectors=SELECTORS):
    return iter_json_projection(
        io.BytesIO(data),
        selectors,
        expected_sha256=hashlib.sha256(data).hexdigest(),
        expected_size=len(data),
        object_audit=observer,
    )


def test_ignored_members_are_reported_in_original_decoded_order():
    data = b'{"ignored":{"nested":[1,2]},"metadata":{"analysis":{"files":[],"unexpected":17}},"findings":[]}'
    audit = []
    events = list(project(data, lambda path, keys: audit.append((path, keys))))
    assert audit == [
        (("metadata", "analysis"), ("files", "unexpected")),
        (("metadata",), ("analysis",)),
        ((), ("ignored", "metadata", "findings")),
    ]
    assert isinstance(events[-1], ProjectionComplete)
    assert not any(
        [
            events[-1].schema_verified,
            events[-1].source_verified,
            events[-1].native_executed,
            events[-1].analysis_cache_eligible,
        ]
    )


def test_absent_and_present_empty_optional_objects_are_distinct():
    audits = []
    for data in (
        b'{"metadata":{},"findings":[]}',
        b'{"metadata":{"analysis":{}},"findings":[]}',
    ):
        seen = {}
        events = list(project(data, lambda path, keys: seen.__setitem__(path, keys)))
        audits.append(seen)
        assert events[-1].counts == (("findings", 0), ("files", 0))
    assert ("metadata", "analysis") not in audits[0]
    assert audits[1][("metadata", "analysis")] == ()


def test_audit_rejection_keeps_prior_records_provisional():
    observed = []

    def reject(path, keys):
        if path == ("metadata", "analysis") and "unexpected" in keys:
            raise ContractError("Unknown closed analysis member")

    with pytest.raises(ContractError, match="Unknown closed"):
        for item in project(
            b'{"findings":[{"id":"provisional"}],"metadata":{"analysis":{"unexpected":1}}}',
            reject,
        ):
            observed.append(item)
    assert observed and not any(
        isinstance(item, ProjectionComplete) for item in observed
    )


def test_audit_keys_decode_escaped_spelling():
    seen = []
    list(
        project(
            b'{"meta\\u0064ata":{"analysis":{}},"findings":[]}',
            lambda p, k: seen.append((p, k)),
        )
    )
    assert ((), ("metadata", "findings")) in seen


def test_invalid_observer_is_rejected_before_input_io():
    class NoRead:
        def read(self, *args):
            raise AssertionError("Invalid declaration must not read source")

    with pytest.raises(ContractError, match="audit"):
        iter_json_projection(
            NoRead(),
            SELECTORS,
            expected_sha256="0" * 64,
            expected_size=1,
            object_audit=17,
        )


@pytest.mark.parametrize(
    "data",
    [
        b'{"findings":[],"extra":1,"extra":2}',
        b'{"findings":[],"extra":1e999}',
        b'{"findings":[],"extra":[}',
    ],
)
def test_observer_does_not_relax_full_ignored_structure(data):
    observed = []
    with pytest.raises(ContractError):
        observed.extend(project(data, lambda p, k: None))
    assert not any(isinstance(item, ProjectionComplete) for item in observed)


def test_default_and_observed_record_streams_agree():
    data = b'{"metadata":{"analysis":{"files":[1,2]}},"findings":[{"a":1}]}'
    plain = list(project(data))
    assert plain == list(project(data, lambda p, k: None))
