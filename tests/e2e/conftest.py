"""Shared fixtures for e2e smoke tests."""
import os
import yaml
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def isolated_e2e_config(tmp_path) -> str:
    """A config.test.yaml clone pointed at a per-test tmp_path instead of the
    shared data/test — pytest cleans tmp_path up on its own, instead of every
    smoke-test run leaving another user behind in a directory that only ever grows.
    Returns the path to the generated config file."""
    with open(os.path.join(PROJECT_ROOT, "config.test.yaml"), encoding="utf-8") as f:
        data = yaml.safe_load(f)
    data["data_root"] = str(tmp_path)

    config_path = tmp_path / "config.test.yaml"
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f)

    return str(config_path)
