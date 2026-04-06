"""Validate .gitlab-ci.yml structure before pushing.

Catches the most common GitLab CI YAML errors locally:
  - Invalid YAML syntax
  - script/before_script/after_script items that aren't strings
  - Missing required keys (stage, script)
  - Invalid stage references

Run: pytest tests/test_gitlab_ci.py -v
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

CI_FILE = Path(__file__).resolve().parent.parent / ".gitlab-ci.yml"

GITLAB_TOP_LEVEL_KEYS = {
    "stages",
    "variables",
    "default",
    "workflow",
    "include",
    "image",
    "services",
    "before_script",
    "after_script",
    "cache",
    "pages",
}


@pytest.fixture(scope="module")
def ci_config() -> dict:
    """Parse the GitLab CI config."""
    assert CI_FILE.exists(), f"{CI_FILE} not found"
    with CI_FILE.open() as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def jobs(ci_config: dict) -> dict[str, dict]:
    """Extract job definitions (non-top-level keys)."""
    return {
        k: v
        for k, v in ci_config.items()
        if k not in GITLAB_TOP_LEVEL_KEYS and isinstance(v, dict)
    }


def test_yaml_parses(ci_config: dict) -> None:
    """YAML must parse without errors."""
    assert isinstance(ci_config, dict), "Root must be a mapping"


def test_stages_defined(ci_config: dict) -> None:
    """stages: key must be present and non-empty."""
    assert "stages" in ci_config
    assert isinstance(ci_config["stages"], list)
    assert len(ci_config["stages"]) > 0


def test_all_jobs_have_stage(jobs: dict[str, dict]) -> None:
    """Every job must declare a stage."""
    for name, job in jobs.items():
        assert "stage" in job, f"Job '{name}' missing 'stage'"


def test_all_job_stages_are_valid(ci_config: dict, jobs: dict[str, dict]) -> None:
    """Every job's stage must be listed in stages:."""
    valid_stages = set(ci_config["stages"])
    for name, job in jobs.items():
        assert job["stage"] in valid_stages, (
            f"Job '{name}' uses stage '{job['stage']}' "
            f"not in {valid_stages}"
        )


def test_all_jobs_have_script(jobs: dict[str, dict]) -> None:
    """Every job must have a script: block."""
    for name, job in jobs.items():
        assert "script" in job, f"Job '{name}' missing 'script'"


def test_script_items_are_strings(jobs: dict[str, dict]) -> None:
    """Every item in script/before_script/after_script must be a string.

    This is the exact check GitLab performs — non-string items cause:
    'config should be a string or a nested array of strings'
    """
    for name, job in jobs.items():
        for field in ("script", "before_script", "after_script"):
            block = job.get(field)
            if block is None:
                continue
            assert isinstance(block, list), (
                f"{name}.{field} must be a list, got {type(block).__name__}"
            )
            for i, item in enumerate(block):
                assert isinstance(item, str), (
                    f"{name}.{field}[{i}] must be a string, "
                    f"got {type(item).__name__}: {repr(item)[:80]}"
                )


def test_no_empty_scripts(jobs: dict[str, dict]) -> None:
    """script: blocks must not be empty."""
    for name, job in jobs.items():
        script = job.get("script", [])
        assert len(script) > 0, f"Job '{name}' has empty script"


def test_needs_reference_existing_jobs(jobs: dict[str, dict]) -> None:
    """Every entry in needs: must reference an existing job."""
    job_names = set(jobs.keys())
    for name, job in jobs.items():
        needs = job.get("needs")
        if needs is None:
            continue
        for need in needs:
            ref = need if isinstance(need, str) else need.get("job", "")
            assert ref in job_names, (
                f"Job '{name}' needs '{ref}' which doesn't exist. "
                f"Available: {sorted(job_names)}"
            )
