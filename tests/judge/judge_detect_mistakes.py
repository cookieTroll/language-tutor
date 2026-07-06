"""
Judge: DetectMistakesSkill (Step 1)

Evaluates fragment detection only — taxonomy tags and corrections are not in scope for this step.

Run:
    pytest tests/judge/judge_detect_mistakes.py -v -s
    LTUT_CONFIG=config.test.yaml pytest tests/judge/judge_detect_mistakes.py -v -s
"""
import json
import os
import pytest

from tests.judge.utils import load_cases, make_llm, run_metadata, strip_markdown_json, write_results

JUDGE_PROMPT = """\
You are evaluating a {level} {language} language error detector (Step 1 of a writing pipeline).
This step's sole job: find erroneous text fragments. It does NOT classify or correct them.

Student text: {user_text}

Expected erroneous fragments:
{expected_fragments}

Detected fragments:
{detected_fragments}

Evaluate:
1. Did the system find a fragment covering each expected error location?
   (Wider fragments are acceptable; only penalise if the fragment has no relation to the error location.)
2. Did it avoid flagging fragments from correct text?

Rules:
- PASS: all expected errors detected, no false positives.
- PARTIAL: some expected errors found but others missed, OR minor false positives present.
- FAIL: no expected errors detected at all, OR correct text was flagged when none expected.
- Score 0.0 to 1.0.

Return JSON only:
{{
  "verdict": "PASS" | "PARTIAL" | "FAIL",
  "score": <float 0.0-1.0>,
  "reasoning": "<one sentence>",
  "missed_errors": ["<expected fragment not detected>", ...],
  "false_positives": ["<detected fragment that is correct {language}>", ...]
}}"""


def _judge(judge_llm, case: dict, detected: list[dict]) -> dict:
    from llm.base import LLMMessage

    expected_fragments = [m["fragment"] for m in case["expected_mistakes"]]
    expected_str = (
        json.dumps(expected_fragments, ensure_ascii=False)
        if expected_fragments
        else "none (text is correct — any detection is a false positive)"
    )
    detected_str = (
        json.dumps([m["fragment"] for m in detected], ensure_ascii=False)
        if detected
        else "none"
    )

    prompt = JUDGE_PROMPT.format(
        level=case["level"],
        language=case["language"].capitalize(),
        user_text=case["user_text"],
        expected_fragments=expected_str,
        detected_fragments=detected_str,
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
    path = write_results(records, "judge_detector", metadata=run_metadata())
    print(f"\nResults written to: {path}")


@pytest.mark.judge
@pytest.mark.parametrize("case", load_cases(), ids=[c["id"] for c in load_cases()])
def test_detect_mistakes(executor_llm, judge_llm, results_collector, case):
    from skills.detect_mistakes.skill import DetectMistakesSkill
    from skills.protocols import SkillInput

    skill = DetectMistakesSkill()
    out = skill.run(
        SkillInput(
            user_id="judge",
            level=case["level"],
            parameters={
                "user_text": case["user_text"],
                "writing_prompt": case["writing_prompt"],
                "language": case["language"],
                "recurring_errors": [],
            },
        ),
        executor_llm,
    )
    detected = out.metadata.get("raw_mistakes", [])

    try:
        verdict = _judge(judge_llm, case, detected)
    except Exception as e:
        verdict = {"verdict": "ERROR", "score": 0.0, "reasoning": str(e), "missed_errors": [], "false_positives": []}

    record = {
        "id": case["id"],
        "description": case["description"],
        "user_text": case["user_text"],
        "expected_mistake_count": case["expected_mistake_count"],
        "expected_fragments": [m["fragment"] for m in case["expected_mistakes"]],
        "detected": detected,
        "executor_success": out.success,
        "verdict": verdict.get("verdict"),
        "score": verdict.get("score"),
        "reasoning": verdict.get("reasoning"),
        "missed_errors": verdict.get("missed_errors", []),
        "false_positives": verdict.get("false_positives", []),
        "judge_prompt": verdict.get("judge_prompt", ""),
    }
    results_collector.append(record)

    print(f"\n[{case['id']}] {case['description']}")
    print(f"  text      : {case['user_text']}")
    print(f"  detected  : {[m['fragment'] for m in detected]}")
    print(f"  verdict   : {verdict.get('verdict')}  score={verdict.get('score')}")
    print(f"  reasoning : {verdict.get('reasoning')}")

    assert verdict.get("verdict") in ("PASS", "PARTIAL"), (
        f"[{case['id']}] FAIL — {verdict.get('reasoning')}\n"
        f"  detected : {[m['fragment'] for m in detected]}\n"
        f"  expected : {[m['fragment'] for m in case['expected_mistakes']]}"
    )
