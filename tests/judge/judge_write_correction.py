"""
Judge: WriteCorrectionSkill (Step 4)

Injects fixture mistakes with stub explanations (isolates write_correction from explain).
Judges whether corrected_text matches expected_corrected_text from the fixture.

Run:
    pytest tests/judge/judge_write_correction.py -v -s
    LTUT_CONFIG=config.test.yaml pytest tests/judge/judge_write_correction.py -v -s
"""
import json
import os
import pytest

from tests.judge.utils import load_cases, make_llm, run_metadata, strip_markdown_json, write_results

JUDGE_PROMPT = """\
You are evaluating a German text correction step (Step 4 of a writing pipeline).
The corrector must apply ONLY the listed corrections to the original text — nothing else.

Student text: {user_text}

Corrections to apply:
{corrections}

Expected corrected text: {expected}
Produced corrected text: {produced}

Evaluate:
1. Does the produced text apply every correction from the list?
2. Does it leave all other parts of the text unchanged?
3. Is the produced text linguistically equivalent to the expected text?
   (Minor surface differences within a corrected span are acceptable if the meaning is the same.)

Rules:
- PASS: produced text matches expected (or is linguistically equivalent).
- PARTIAL: most corrections applied but one minor addition or omission present.
- FAIL: corrections not applied, text heavily modified, or output is completely wrong.
- Score 0.0 to 1.0.

Return JSON only:
{{
  "verdict": "PASS" | "PARTIAL" | "FAIL",
  "score": <float 0.0-1.0>,
  "reasoning": "<one sentence>",
  "unapplied_corrections": ["<correction not reflected in output>", ...],
  "unwanted_changes": ["<text changed without a correction to justify it>", ...]
}}"""


def _judge(judge_llm, case: dict, produced_text: str) -> dict:
    from llm.base import LLMMessage

    corrections = [
        {"fragment": m["fragment"], "correction": m["correction"]}
        for m in case["expected_mistakes"]
    ]
    prompt = JUDGE_PROMPT.format(
        user_text=case["user_text"],
        corrections=(
            json.dumps(corrections, ensure_ascii=False)
            if corrections
            else "none (no errors — text should be returned unchanged)"
        ),
        expected=case["expected_corrected_text"],
        produced=produced_text,
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
    path = write_results(records, "judge_corrector", metadata=run_metadata())
    print(f"\nResults written to: {path}")


@pytest.mark.judge
@pytest.mark.parametrize("case", load_cases(), ids=[c["id"] for c in load_cases()])
def test_write_correction(executor_llm, judge_llm, results_collector, case):
    from skills.write_correction.skill import WriteCorrectionSkill
    from skills.protocols import SkillInput

    # Stub explanations so write_correction can run isolated from explain_mistakes
    explained_mistakes = [
        {
            "fragment": m["fragment"],
            "error_tag": m["error_tag"],
            "correction": m["correction"],
            "explanation": (
                f"Replace '{m['fragment']}' with '{m['correction']}' "
                f"({m['error_tag'].replace('_', ' ')})."
            ),
        }
        for m in case["expected_mistakes"]
    ]

    skill = WriteCorrectionSkill()
    out = skill.run(
        SkillInput(
            user_id="judge",
            level=case["level"],
            parameters={
                "user_text": case["user_text"],
                "explained_mistakes": explained_mistakes,
                "language": case["language"],
            },
        ),
        executor_llm,
    )
    produced_text = out.metadata.get("corrected_text", "")

    try:
        verdict = _judge(judge_llm, case, produced_text)
    except Exception as e:
        verdict = {"verdict": "ERROR", "score": 0.0, "reasoning": str(e), "unapplied_corrections": [], "unwanted_changes": []}

    record = {
        "id": case["id"],
        "description": case["description"],
        "user_text": case["user_text"],
        "explained_mistakes": explained_mistakes,
        "expected_corrected_text": case["expected_corrected_text"],
        "produced_corrected_text": produced_text,
        "executor_success": out.success,
        "verdict": verdict.get("verdict"),
        "score": verdict.get("score"),
        "reasoning": verdict.get("reasoning"),
        "unapplied_corrections": verdict.get("unapplied_corrections", []),
        "unwanted_changes": verdict.get("unwanted_changes", []),
        "judge_prompt": verdict.get("judge_prompt", ""),
    }
    results_collector.append(record)

    print(f"\n[{case['id']}] {case['description']}")
    print(f"  expected  : {case['expected_corrected_text']}")
    print(f"  produced  : {produced_text}")
    print(f"  verdict   : {verdict.get('verdict')}  score={verdict.get('score')}")
    print(f"  reasoning : {verdict.get('reasoning')}")

    assert verdict.get("verdict") in ("PASS", "PARTIAL"), (
        f"[{case['id']}] FAIL — {verdict.get('reasoning')}\n"
        f"  expected : {case['expected_corrected_text']}\n"
        f"  produced : {produced_text}"
    )
