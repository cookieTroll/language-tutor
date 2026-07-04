"""
Judge: VerifyMistakesSkill (Step 1.5)

Deterministic, not LLM-judged — each fixture case has a known-correct keep/reject
split (expected_keep / expected_reject), so this checks the executor's verdicts
directly against ground truth rather than routing through a second judge LLM call
(same pattern as judge_grade_exercises.py: separate deterministic ground-truth
assertions from the genuinely subjective piece — verification here IS the
deterministic piece, there's nothing subjective left to judge).

Run:
    pytest tests/judge/judge_verify_mistakes.py -v -s -m judge
    LTUT_CONFIG=config.test.yaml pytest tests/judge/judge_verify_mistakes.py -v -s -m judge
"""
import json
import os
import pytest

from tests.judge.utils import make_llm, write_results, PROJECT_ROOT

FIXTURE_PATH = os.path.join(PROJECT_ROOT, "tests", "fixtures", "verify_mistakes_cases.json")


def load_cases() -> list[dict]:
    with open(FIXTURE_PATH, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def executor_llm():
    return make_llm(os.environ.get("LTUT_CONFIG", "config.test.yaml"))


@pytest.fixture(scope="module")
def results_collector():
    records = []
    yield records
    path = write_results(records, "judge_verify_mistakes")
    print(f"\nResults written to: {path}")


@pytest.mark.judge
@pytest.mark.parametrize("case", load_cases(), ids=[c["id"] for c in load_cases()])
def test_verify_mistakes(executor_llm, results_collector, case):
    from skills.verify_mistakes.skill import VerifyMistakesSkill
    from skills.protocols import SkillInput

    skill = VerifyMistakesSkill()
    out = skill.run(
        SkillInput(
            user_id="judge",
            level=case.get("level", "b1"),
            parameters={
                "raw_mistakes": case["candidates"],
                "user_text": case["user_text"],
                "language": case["language"],
            },
        ),
        executor_llm,
    )

    kept_fragments = {m["fragment"] for m in out.metadata.get("verified_mistakes", [])}
    expected_keep = set(case["expected_keep"])
    expected_reject = set(case["expected_reject"])

    wrongly_kept = kept_fragments & expected_reject      # false positive survived verification
    wrongly_dropped = expected_keep - kept_fragments     # genuine error wrongly dropped

    record = {
        "id": case["id"],
        "description": case["description"],
        "executor_success": out.success,
        "kept": sorted(kept_fragments),
        "expected_keep": sorted(expected_keep),
        "expected_reject": sorted(expected_reject),
        "wrongly_kept": sorted(wrongly_kept),
        "wrongly_dropped": sorted(wrongly_dropped),
    }
    results_collector.append(record)

    print(f"\n[{case['id']}] {case['description']}")
    print(f"  kept            : {sorted(kept_fragments)}")
    print(f"  expected_keep   : {sorted(expected_keep)}")
    print(f"  expected_reject : {sorted(expected_reject)}")

    assert out.success, f"[{case['id']}] skill call failed: {out.metadata.get('error')}"
    assert not wrongly_kept, f"[{case['id']}] false positive survived verification: {wrongly_kept}"
    assert not wrongly_dropped, f"[{case['id']}] genuine error wrongly dropped: {wrongly_dropped}"
