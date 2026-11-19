"""Lazy original arrays compare by checked contents without eager copies."""

from copy import deepcopy

import pytest

from cppulse.errors import ContractError
from test_native_report_reader import opened, report


def test_original_json_comparison_is_symmetric_and_retains_order(tmp_path):
    original = report()
    with opened(tmp_path, original) as reader:
        assert original == reader.document
        assert reader.document == original
        changed = deepcopy(original)
        changed["findings"][0]["message"] += " changed"
        assert reader.document != changed
        assert changed != reader.document
        assert reader.document["findings"] != []
        assert reader.document["findings"] != "not an array"


def test_comparison_refuses_closed_reader_even_for_empty_array(tmp_path):
    original = report()
    original["findings"] = []
    with opened(tmp_path, original) as reader:
        array = reader.document["findings"]
        assert array == []
    with pytest.raises(ContractError, match="reader is closed"):
        assert array == []
