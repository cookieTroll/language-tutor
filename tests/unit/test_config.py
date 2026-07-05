import pytest
from config import load_config

# No test previously loaded the actual committed config files — only mocked paths
# via e2e/judge helpers touch load_config. This would have caught the
# requirements.txt/pyproject.toml dependency-drift symptom earlier and guards
# against a future config typo shipping silently.


@pytest.mark.parametrize(
    "path,env,expected_provider",
    [
        ("config.yaml", {}, "ollama"),
        ("config.test.yaml", {}, "ollama"),
        ("config.gemini.yaml", {"GEMINI_API_KEY": "test-key"}, "gemini"),
        ("config.vertex.yaml", {"GCP_PROJECT": "test-project", "GCP_REGION": "europe-west1"}, "vertex"),
    ],
)
def test_load_config_real_files(monkeypatch, path, env, expected_provider):
    for var, value in env.items():
        monkeypatch.setenv(var, value)
    config = load_config(path)
    assert config.llm.provider == expected_provider
