"""Genuine three-test pytest JUnit fixture with deliberately mixed outcomes."""
import pytest


def test_passed():
    assert 1 + 1 == 2


def test_failed():
    assert 1 + 1 == 3


@pytest.mark.skip(reason="Deliberate skipped fixture testcase")
def test_skipped():
    raise AssertionError("Skipped body must not execute")
