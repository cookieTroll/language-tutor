"""
End-to-end smoke test — runs the full CLI session against a live LLM.

Requires Ollama (or another configured provider) to be running.
Excluded from unit test runs; execute manually:

    pytest tests/e2e/ -v -s
"""
import os
import subprocess
import sys
import time

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TIMEOUT = 180  # seconds — LLM pipeline has 6 steps


@pytest.mark.e2e
def test_full_writing_session():
    """New user → German A2 → writing session → session saved."""
    user_id = f"smoke_{int(time.time())}"

    # Input sequence for a brand-new user (no prior profile):
    #   1. user ID
    #   2. language
    #   3. CEFR level
    #   4. confirm writing module (Enter = yes)
    #   5. one line of essay text
    #   6. empty line = submit
    #   7. empty line = exit follow-up phase
    #   8. decline another session
    inputs = "\n".join([
        user_id,
        "german",
        "a2",
        "",
        "Ich stehe morgens um sieben Uhr auf. Dann frühstücke ich mit meiner Familie.",
        "",
        "",
        "n",
    ]) + "\n"

    env = {**os.environ, "LTUT_CONFIG": "config.test.yaml", "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run(
        [sys.executable, "-m", "ui.cli"],
        input=inputs,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=TIMEOUT,
        cwd=PROJECT_ROOT,
        env=env,
    )

    assert result.returncode == 0, (
        f"CLI exited {result.returncode}\n--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )
    assert "Session successfully saved!" in result.stdout, (
        f"Session did not complete.\n--- stdout ---\n{result.stdout}"
    )
