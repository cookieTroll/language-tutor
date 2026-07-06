"""
Judge: ExplainMistakesSkill (Step 3)

Injects fixture classified_mistakes directly (isolates explain from classify).
No ground-truth explanation — the judge evaluates quality semantically.

Run:
    pytest tests/judge/judge_explain_mistakes.py -v -s
    LTUT_CONFIG=config.test.yaml pytest tests/judge/judge_explain_mistakes.py -v -s
"""
import json
import os
import pytest

from tests.judge.utils import load_cases, make_llm, run_metadata, strip_markdown_json, write_results

JUDGE_PROMPT = """\
You are evaluating explanations written by a German language teacher (Step 3 of a writing pipeline).
The teacher's job: explain each grammar mistake to the learner in plain English at their CEFR level.

Student text: {user_text}
Learner level: {level}

Classified mistakes fed to the explainer:
{classified_mistakes}

Produced explanations:
{produced_explanations}

Evaluate each explanation:
1. Is it non-empty and directly relevant to the specific error (fragment + error_tag)?
2. Is the language accessible for a {level} learner (not overly technical, not too vague)?
3. Does it explain *why* the rule applies, not just restate what the correction is?

Rules:
- PASS: all explanations are relevant, level-appropriate, and convey a clear "why".
- PARTIAL: most are good but one is vague, off-topic, or only restates the correction.
- FAIL: explanations are absent, irrelevant, or clearly wrong about the grammar rule.
- Score 0.0 to 1.0.

Return JSON only:
{{
  "verdict": "PASS" | "PARTIAL" | "FAIL",
  "score": <float 0.0-1.0>,
  "reasoning": "<one sentence>",
  "weak_explanations": ["<fragment>: <issue with its explanation>", ...]
}}"""


def _judge(judge_llm, case: dict, classified_input: list[dict], produced: list[dict]) -> dict:
    from llm.base import LLMMessage

    prompt = JUDGE_PROMPT.format(
        user_text=case["user_text"],
        level=case["level"].upper(),
        classified_mistakes=json.dumps(classified_input, ensure_ascii=False),
        produced_explanations=json.dumps(produced, ensure_ascii=False) if produced else "none",
    )
    response = judge_llm.complete([LLMMessage(role="user", content=prompt)], temperature=0.0)
    result = json.loads(strip_markdown_json(response.text.strip()))
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
    path = write_results(records, "judge_explainer", metadata=run_metadata())
    print(f"\nResults written to: {path}")


@pytest.mark.judge
@pytest.mark.parametrize("case", load_cases(), ids=[c["id"] for c in load_cases()])
def test_explain_mistakes(executor_llm, judge_llm, results_collector, case):
    from skills.explain_mistakes.skill import ExplainMistakesSkill
    from skills.protocols import SkillInput

    if not case["expected_mistakes"]:
        pytest.skip("No mistakes to explain")

    classified_mistakes = [
        {
            "fragment": m["fragment"],
            "error_tag": m["error_tag"],
            "correction": m["correction"],
        }
        for m in case["expected_mistakes"]
    ]

    skill = ExplainMistakesSkill()
    out = skill.run(
        SkillInput(
            user_id="judge",
            level=case["level"],
            parameters={
                "classified_mistakes": classified_mistakes,
                "language": case["language"],
            },
        ),
        executor_llm,
    )
    produced = out.metadata.get("explained_mistakes", [])

    try:
        verdict = _judge(judge_llm, case, classified_mistakes, produced)
    except Exception as e:
        verdict = {"verdict": "ERROR", "score": 0.0, "reasoning": str(e), "weak_explanations": []}

    record = {
        "id": case["id"],
        "description": case["description"],
        "user_text": case["user_text"],
        "level": case["level"],
        "classified_input": classified_mistakes,
        "produced": produced,
        "executor_success": out.success,
        "verdict": verdict.get("verdict"),
        "score": verdict.get("score"),
        "reasoning": verdict.get("reasoning"),
        "weak_explanations": verdict.get("weak_explanations", []),
        "judge_prompt": verdict.get("judge_prompt", ""),
    }
    results_collector.append(record)

    print(f"\n[{case['id']}] {case['description']}")
    print(f"  explanations: {[m.get('explanation', '')[:60] + '...' for m in produced]}")
    print(f"  verdict   : {verdict.get('verdict')}  score={verdict.get('score')}")
    print(f"  reasoning : {verdict.get('reasoning')}")

    assert verdict.get("verdict") in ("PASS", "PARTIAL"), (
        f"[{case['id']}] FAIL — {verdict.get('reasoning')}\n"
        f"  weak: {verdict.get('weak_explanations', [])}"
    )
