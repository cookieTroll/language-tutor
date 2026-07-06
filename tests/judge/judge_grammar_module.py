"""
Judge: GrammarModule (full 2a-iv pipeline — select_grammar/manual override -> dump_grammar
-> generate_exercises -> collect answers -> grade_exercises -> score)

Runs a full module session against a real (local) LLM, with a scripted IOHandler
that always accepts the select_grammar suggestion (topic_input="") and submits a
blank answer block. Blank answers make the outcome deterministic — everything
must come back incorrect — so the run can be checked structurally in Python
without needing to guess what the model will generate. The LLM judge is only
used for the one genuinely subjective question: are the generated exercises
actually on-topic and level-appropriate, i.e. did the topic thread correctly
from select_grammar through dump_grammar and generate_exercises without drift?

Run:
    pytest tests/judge/judge_grammar_module.py -v -s
    LTUT_CONFIG=config.test.yaml pytest tests/judge/judge_grammar_module.py -v -s
"""
import json
import os
import yaml
import pytest

from tests.judge.utils import make_llm, run_metadata, strip_markdown_json, write_results, PROJECT_ROOT


FIXTURE_PATH = os.path.join(PROJECT_ROOT, "tests", "fixtures", "grammar_cases.json")


def load_cases() -> list[dict]:
    with open(FIXTURE_PATH, encoding="utf-8") as f:
        return json.load(f)


def _load_taxonomy_tags() -> set[str]:
    path = os.path.join(PROJECT_ROOT, "lang", "maps", "taxonomy", "german_taxonomy_v1.yaml")
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return set(data["tags"].keys())


_TAXONOMY_TAGS = _load_taxonomy_tags()


class ScriptedIOHandler:
    """Minimal IOHandler double: always accepts the select_grammar suggestion,
    submits a blank answer block, and declines the "another exercise?"
    continuation prompt so the session runs exactly one round."""

    show_cli_hints = False

    def __init__(self, topic_input: str = "", answer_block: str = ""):
        self._topic_input = topic_input
        self._answer_block = answer_block
        self.output_lines: list[str] = []

    def output(self, text: str = "") -> None:
        self.output_lines.append(text)

    def prompt(self, text: str = "") -> str:
        if text.startswith("\nAnother exercise on"):
            return "n"
        return self._topic_input

    def prompt_block(self, text: str = "") -> str:
        return self._answer_block

    def render_evaluation(self, data: dict) -> None:
        pass

    def start_timer(self, label: str = "Writing") -> None:
        pass

    def stop_timer(self) -> None:
        pass


JUDGE_PROMPT = """\
You are evaluating whether a set of German grammar exercises are a coherent,
on-topic continuation of a selected grammar topic and explanation — i.e. did
the topic thread correctly through the pipeline (topic selection -> reference
explanation -> exercise generation) without drifting to something unrelated.

Level: {level}
Selected topic: {topic}
Explanation excerpt: {explanation_excerpt}

Generated exercise prompts:
{exercise_prompts}

Evaluate:
1. Do the exercises clearly relate to the selected topic (not a different,
   unrelated grammar point)?
2. Are they reasonably appropriate for a {level} learner?

Rules:
- PASS: exercises are clearly on-topic and level-appropriate.
- PARTIAL: mostly on-topic, one exercise is a stretch.
- FAIL: exercises are about a different topic than selected, or wildly
  mismatched to the level.

Return JSON only. No markdown.
{{
  "verdict": "PASS" | "PARTIAL" | "FAIL",
  "score": <float 0.0-1.0>,
  "reasoning": "<one sentence>"
}}"""


def _judge(judge_llm, case: dict, topic: str, explanation: str, exercises: list[dict]) -> dict:
    from llm.base import LLMMessage

    prompt = JUDGE_PROMPT.format(
        level=case["level"].upper(),
        topic=topic,
        explanation_excerpt=explanation[:400],
        exercise_prompts="\n".join(f"  - {ex['prompt']}" for ex in exercises),
    )
    response = judge_llm.complete([LLMMessage(role="user", content=prompt)], temperature=0.0)
    text = strip_markdown_json(response.text.strip())
    result, _ = json.JSONDecoder().raw_decode(text)
    result["judge_prompt"] = prompt
    return result


@pytest.fixture(scope="module")
def executor_llm():
    return make_llm(os.environ.get("LTUT_CONFIG", "config.test.yaml"))


@pytest.fixture(scope="module")
def judge_llm():
    config = os.environ.get("LTUT_JUDGE_CONFIG", os.environ.get("LTUT_CONFIG", "config.test.yaml"))
    return make_llm(config)


@pytest.fixture(scope="module")
def results_collector():
    records = []
    yield records
    path = write_results(records, "judge_grammar_module", metadata=run_metadata())
    print(f"\nResults written to: {path}")


@pytest.mark.judge
@pytest.mark.parametrize("case", load_cases(), ids=[c["id"] for c in load_cases()])
def test_grammar_module_session(executor_llm, judge_llm, results_collector, case):
    from modules.grammar.agent import GrammarModule
    from modules.protocols import ModuleContext

    ctx = ModuleContext(
        user_id="judge",
        language=case["language"],
        level=case["level"],
        recent_sessions=[],
        error_frequency=case["error_frequency"],
        recent_topics=case["recent_topics"],
        vocab_flags=[],
        parameters={},
    )
    io = ScriptedIOHandler(topic_input="", answer_block="")

    result, session_content = GrammarModule().run(ctx, executor_llm, io)

    # --- Structural checks (no LLM judge) — blank answers make these deterministic ---
    assert result.module == "grammar"
    assert session_content.topic, f"[{case['id']}] no topic selected"
    assert session_content.items, f"[{case['id']}] no exercises produced"
    assert session_content.score == 0.0, (
        f"[{case['id']}] blank answers must score 0.0, got {session_content.score}"
    )
    for item in session_content.items:
        assert item["correct"] is False, f"[{case['id']}] blank answer marked correct: {item}"
        assert item["feedback"], f"[{case['id']}] missing feedback for wrong item: {item}"
        assert item["error_tag"] in _TAXONOMY_TAGS, (
            f"[{case['id']}] invalid error_tag: {item['error_tag']}"
        )
    assert len(result.errors) == len(session_content.items)

    try:
        verdict = _judge(judge_llm, case, session_content.topic, session_content.explanation, session_content.items)
    except Exception as e:
        verdict = {"verdict": "ERROR", "score": 0.0, "reasoning": str(e)}

    record = {
        "id": case["id"],
        "description": case["description"],
        "topic": session_content.topic,
        "scope": session_content.scope,
        "level": case["level"],
        "exercise_count": len(session_content.items),
        "score": session_content.score,
        "verdict": verdict.get("verdict"),
        "judge_score": verdict.get("score"),
        "reasoning": verdict.get("reasoning"),
        "judge_prompt": verdict.get("judge_prompt", ""),
    }
    results_collector.append(record)

    print(f"\n[{case['id']}] {case['description']}")
    print(f"  topic: {session_content.topic} (scope={session_content.scope})")
    print(f"  exercises: {len(session_content.items)}  score={session_content.score}")
    print(f"  verdict: {verdict.get('verdict')}  score={verdict.get('score')}  — {verdict.get('reasoning')}")

    assert verdict.get("verdict") in ("PASS", "PARTIAL"), (
        f"[{case['id']}] FAIL — {verdict.get('reasoning')}"
    )
