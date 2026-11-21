"""Versioned exact-duplication counts are distinct from the native base profile."""

from __future__ import annotations

from copy import deepcopy

import pytest

from cppulse.contracts import validate
from cppulse.errors import ContractError
from tests.test_maintenance_metrics_contract import metric_document


def duplication_metrics():
    document = metric_document()
    row = deepcopy(document["items"][0])
    row.update(
        id="duplicate-tokens",
        metric="duplicate_tokens",
        metric_version="cppulse-exact-duplicates-30-v1",
        units="tokens",
        value=30,
    )
    document["items"].append(row)
    return document


def test_separate_duplication_method_accepts_measured_nonnegative_token_count():
    validate("analysis_metrics", duplication_metrics())


@pytest.mark.parametrize(
    "mutation", ["negative", "fractional", "wrong_units", "function_symbol"]
)
def test_duplication_count_units_and_scope_are_not_generic_escape_hatches(mutation):
    document = duplication_metrics()
    row = document["items"][-1]
    if mutation == "negative":
        row["value"] = -1
    elif mutation == "fractional":
        row["value"] = 2.5
    elif mutation == "wrong_units":
        row["units"] = "probability"
    else:
        row["symbol"] = "c:@F@f#"
    with pytest.raises(ContractError):
        validate("analysis_metrics", document)
