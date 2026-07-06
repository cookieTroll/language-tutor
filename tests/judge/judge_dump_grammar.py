"""
Judge: DumpGrammarSkill

Runs the skill against fixture topics and judges the produced markdown
explanation for factual correctness and completeness against the reference
structure requested in the prompt (rule, table, examples, common mistakes).

Run:
    pytest tests/judge/judge_dump_grammar.py -v -s
    LTUT_CONFIG=config.test.yaml pytest tests/judge/judge_dump_grammar.py -v -s
"""
import json
import os
import pytest

from tests.judge.utils import make_llm, run_metadata, strip_markdown_json, write_results, PROJECT_ROOT


FIXTURE_PATH = os.path.join(PROJECT_ROOT, "tests", "fixtures", "dump_grammar_cases.json")


def load_cases() -> list[dict]:
    with open(FIXTURE_PATH, encoding="utf-8") as f:
        return json.load(f)


JUDGE_PROMPT = """\
You are evaluating a German grammar reference explanation, written for a learner
by a grammar-dump skill. It should read like a textbook entry: thorough, accurate,
and structured for reference use (not a quick note).

Topic: "{topic}"
Target level: {level}
Expected table content: {table_hint}

--- PRODUCED EXPLANATION (markdown) ---
{explanation}

--- EVALUATION ---
Check all of the following:
1. FACTUAL ACCURACY — is the German grammar rule stated correctly? Are the example
   sentences grammatically correct German with accurate translations? This is the
   most important check — a fluent, well-formatted explanation that is factually
   wrong must FAIL.
2. STRUCTURE — does it include: a clear core rule statement, a table (matching
   the expected table content above) if the topic calls for one, at least 4
   example sentences with translations, and a "common mistakes" section?
3. LEVEL FIT — is it written in a way appropriate for a {level} learner (not
   wildly above or below)?

Rules:
- PASS: factually correct, all structural elements present, reasonably level-appropriate.
- PARTIAL: factually correct but missing one structural element (e.g. no explicit
  mistakes section, fewer than 4 examples), or minor level mismatch.
- FAIL: contains a factual grammar error, or missing multiple structural elements.

Return JSON only. No markdown.
{{
  "verdict": "PASS" | "PARTIAL" | "FAIL",
  "score": <float 0.0-1.0>,
  "reasoning": "<one sentence>",
  "factual_issues": ["<specific grammar error found, if any>"],
  "missing_elements": ["<structural element missing, if any>"]
}}"""


def _judge(judge_llm, case: dict, explanation: str) -> dict:
    from llm.base import LLMMessage

    prompt = JUDGE_PROMPT.format(
        topic=case["topic"],
        level=case["level"].upper(),
        table_hint=case["table_hint"],
        explanation=explanation,
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
    path = write_results(records, "judge_dump_grammar", metadata=run_metadata())
    print(f"\nResults written to: {path}")


@pytest.mark.judge
@pytest.mark.parametrize("case", load_cases(), ids=[c["id"] for c in load_cases()])
def test_dump_grammar(executor_llm, judge_llm, results_collector, case):
    from skills.dump_grammar.skill import DumpGrammarSkill
    from skills.protocols import SkillInput

    skill = DumpGrammarSkill()
    out = skill.run(
        SkillInput(
            user_id="judge",
            level=case["level"],
            parameters={"topic": case["topic"], "language": case["language"]},
        ),
        executor_llm,
    )

    assert out.success, f"[{case['id']}] skill call failed: {out.metadata.get('error')}"
    explanation = out.metadata["explanation"]
    assert explanation, f"[{case['id']}] empty explanation"

    try:
        verdict = _judge(judge_llm, case, explanation)
    except Exception as e:
        verdict = {"verdict": "ERROR", "score": 0.0, "reasoning": str(e), "factual_issues": [], "missing_elements": []}

    record = {
        "id": case["id"],
        "description": case["description"],
        "topic": case["topic"],
        "level": case["level"],
        "explanation": explanation,
        "verdict": verdict.get("verdict"),
        "score": verdict.get("score"),
        "reasoning": verdict.get("reasoning"),
        "factual_issues": verdict.get("factual_issues", []),
        "missing_elements": verdict.get("missing_elements", []),
        "judge_prompt": verdict.get("judge_prompt", ""),
    }
    results_collector.append(record)

    print(f"\n[{case['id']}] {case['description']}")
    print(f"  explanation length: {len(explanation)} chars")
    print(f"  verdict   : {verdict.get('verdict')}  score={verdict.get('score')}")
    print(f"  reasoning : {verdict.get('reasoning')}")
    if verdict.get("factual_issues"):
        print(f"  factual_issues  : {verdict['factual_issues']}")
    if verdict.get("missing_elements"):
        print(f"  missing_elements: {verdict['missing_elements']}")

    assert verdict.get("verdict") in ("PASS", "PARTIAL"), (
        f"[{case['id']}] FAIL — {verdict.get('reasoning')}\n"
        f"  factual_issues: {verdict.get('factual_issues', [])}\n"
        f"  explanation: {explanation[:500]}"
    )
