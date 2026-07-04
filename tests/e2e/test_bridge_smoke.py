"""
End-to-end smoke test for the 2a-vii writing<->grammar bridge — runs two chained
CLI sessions against a live LLM, seeded so the bridge is guaranteed to fire instead
of depending on what a live evaluator happens to flag.

Requires Ollama (or another configured provider) to be running.
Excluded from unit test runs; execute manually:

    pytest tests/e2e/test_bridge_smoke.py -v -s
"""
import os
import subprocess
import sys
import time

import pytest

from tests.e2e.seed_helpers import seed_recurring_error

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TIMEOUT = 420  # seconds — writing's 6-step pipeline + grammar's explain/generate/grade, chained
TAG = "verb_conjugation"
GRAMMAR_TOPIC = "Present tense — regular verbs"  # exact curated match, skips select_grammar's LLM call


@pytest.mark.e2e
def test_writing_to_grammar_bridge_chains_live(isolated_e2e_config):
    """Seed a recurring verb_conjugation error, reproduce it in a live writing
    session, accept the resulting next_actions prompt, and confirm a grammar
    session actually starts within the same CLI process (forced_recommendation)."""
    user_id = f"bridge_smoke_{int(time.time())}"
    seed_recurring_error(user_id, TAG, count=2, config_path=isolated_e2e_config)

    inputs = "\n".join([
        user_id,
        "",                                  # continue studying german (seeded active profile)
        "",                                  # keep level a1
        "",                                  # accept the recommended (default) writing module
        "My day at school",                  # manual topic — skips topic_picker's LLM call
        "Ich gehen jeden Tag zur Schule.",    # deliberate verb_conjugation mistakes
        "Du gehen auch zur Schule und lernen Deutsch.",
        "",                                  # blank line submits the essay
        "",                                  # blank line exits the follow-up phase
        "y",                                 # accept "Start grammar practice on '...' now?"
        "",                                  # chained session: continue studying german
        "",                                  # chained session: keep level a1
        GRAMMAR_TOPIC,                       # manual grammar topic — skips select_grammar's LLM call
        "test", "test", "test", "test", "test",  # dummy answers; padded/truncated regardless of count
        "",                                  # blank line submits the answer block
        "n",                                 # decline another session — ends the CLI loop
    ]) + "\n"

    env = {**os.environ, "LTUT_CONFIG": isolated_e2e_config, "PYTHONIOENCODING": "utf-8"}
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
    out = result.stdout
    assert out.count("Session successfully saved!") == 2, (
        f"Expected two completed sessions (writing + chained grammar).\n--- stdout ---\n{out}"
    )
    assert "Start grammar practice" in out, (
        f"writing->grammar next_actions prompt never appeared.\n--- stdout ---\n{out}"
    )
    assert "GRAMMAR SESSION" in out, (
        f"Chained grammar session never actually started.\n--- stdout ---\n{out}"
    )
