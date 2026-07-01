"""
Judge: GradeExercisesSkill

Runs the skill against fixture batches. Correctness is checked deterministically
against each fixture item's curated `expected_correct` ground truth (these are
clear-cut German grammar judgments, not a matter of LLM opinion) — the LLM judge
is only used for the more subjective check: is the feedback for wrong answers
actually grounded and useful, not generic or hallucinated?

Run:
    pytest tests/judge/judge_grade_exercises.py -v -s
    LTUT_CONFIG=config.test.yaml pytest tests/judge/judge_grade_exercises.py -v -s
"""
import json
import os
import pytest

from tests.judge.utils import make_llm, strip_markdown_json, write_results, PROJECT_ROOT


FIXTURE_PATH = os.path.join(PROJECT_ROOT, "tests", "fixtures", "grade_exercises_cases.json")


def load_cases() -> list[dict]:
    with open(FIXTURE_PATH, encoding="utf-8") as f:
        return json.load(f)


JUDGE_PROMPT = """\
You are evaluating feedback text generated for a wrong answer in a German
grammar exercise (learner level: {level}, topic: "{topic}").

Exercise prompt: {prompt}
Reference correct answer: {correct_answer}
Student's (wrong) answer: {user_answer}

--- PRODUCED FEEDBACK ---
{feedback}

--- EVALUATION ---
1. Is the feedback grounded in the actual exercise (references the specific
   error, not generic advice)?
2. Is it factually correct — does it correctly explain why the student's
   answer is wrong?
3. Is it concise (1-3 sentences) and appropriate for a {level} learner?

Rules:
- PASS: grounded, factually correct, appropriately concise.
- PARTIAL: correct but vague, or slightly verbose.
- FAIL: factually wrong explanation, or generic/hallucinated (doesn't
  reference the actual exercise).

Return JSON only. No markdown.
{{
  "verdict": "PASS" | "PARTIAL" | "FAIL",
  "score": <float 0.0-1.0>,
  "reasoning": "<one sentence>"
}}"""


def _judge_feedback(judge_llm, case: dict, item: dict, feedback: str) -> dict:
    from llm.base import LLMMessage

    prompt = JUDGE_PROMPT.format(
        level=case["level"].upper(),
        topic=case["topic"],
        prompt=item["prompt"],
        correct_answer=item["correct_answer"],
        user_answer=item["user_answer"],
        feedback=feedback,
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
    path = write_results(records, "judge_grade_exercises")
    print(f"\nResults written to: {path}")


@pytest.mark.judge
@pytest.mark.parametrize("case", load_cases(), ids=[c["id"] for c in load_cases()])
def test_grade_exercises(executor_llm, judge_llm, results_collector, case):
    from skills.grade_exercises.skill import GradeExercisesSkill
    from skills.protocols import SkillInput

    # Strip the fixture's ground-truth annotation before sending to the skill —
    # it must judge blind, the same as it would from the real module.
    items_by_index = {item["index"]: item for item in case["items"]}
    skill_items = [
        {k: v for k, v in item.items() if k != "expected_correct"}
        for item in case["items"]
    ]

    skill = GradeExercisesSkill()
    out = skill.run(
        SkillInput(
            user_id="judge",
            level=case["level"],
            parameters={"items": skill_items, "language": case["language"]},
        ),
        executor_llm,
    )

    assert out.success, f"[{case['id']}] skill call failed: {out.metadata.get('error')}"
    results = out.metadata["results"]
    assert len(results) == len(case["items"]), f"[{case['id']}] result count mismatch"

    # --- Structural checks (no LLM) — regression guard on the skill's own contract ---
    mismatches = []
    feedback_records = []
    for r in results:
        item = items_by_index[r["index"]]
        expected_correct = item["expected_correct"]

        if item["already_known_wrong"]:
            assert r["correct"] is False, (
                f"[{case['id']}] index {r['index']}: already_known_wrong item must be forced correct=False"
            )

        if r["correct"]:
            assert r["feedback"] == "", f"[{case['id']}] index {r['index']}: feedback must be empty when correct"
        else:
            assert r["feedback"], f"[{case['id']}] index {r['index']}: feedback must be non-empty when incorrect"
            feedback_records.append((item, r["feedback"]))

        if r["correct"] != expected_correct:
            mismatches.append(
                f"index {r['index']}: expected correct={expected_correct}, got {r['correct']} "
                f"(prompt: {item['prompt']!r})"
            )

    # --- LLM judge — feedback quality only, for items that produced feedback ---
    feedback_verdicts = []
    for item, feedback in feedback_records:
        try:
            verdict = _judge_feedback(judge_llm, case, item, feedback)
        except Exception as e:
            verdict = {"verdict": "ERROR", "score": 0.0, "reasoning": str(e)}
        feedback_verdicts.append({"index": item["index"], **verdict})

    record = {
        "id": case["id"],
        "description": case["description"],
        "topic": case["topic"],
        "level": case["level"],
        "results": results,
        "correctness_mismatches": mismatches,
        "feedback_verdicts": feedback_verdicts,
    }
    results_collector.append(record)

    print(f"\n[{case['id']}] {case['description']}")
    for r in results:
        item = items_by_index[r["index"]]
        print(f"  index={r['index']} correct={r['correct']} (expected={item['expected_correct']})")
    if mismatches:
        print(f"  correctness_mismatches: {mismatches}")
    for fv in feedback_verdicts:
        print(f"  feedback[{fv['index']}] verdict={fv.get('verdict')} score={fv.get('score')} — {fv.get('reasoning')}")

    assert not mismatches, f"[{case['id']}] correctness judgment errors:\n  " + "\n  ".join(mismatches)
    bad_feedback = [fv for fv in feedback_verdicts if fv.get("verdict") not in ("PASS", "PARTIAL")]
    assert not bad_feedback, f"[{case['id']}] feedback quality FAIL: {bad_feedback}"
