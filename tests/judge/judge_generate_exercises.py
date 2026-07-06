"""
Judge: GenerateExercisesSkill

Runs the skill against fixture topics and judges the produced exercise set.
Two layers of checking:
  1. Structural (plain Python, no LLM): every error_tag must be a valid taxonomy
     tag and grading must match the fixed exercise_type -> grading mapping —
     both already enforced by the skill itself, checked here as a regression
     guard, not a discovery mechanism.
  2. LLM judge: are the exercises factually correct German, well-targeted at
     the stated error_tag, and level-appropriate?

Run:
    pytest tests/judge/judge_generate_exercises.py -v -s
    LTUT_CONFIG=config.test.yaml pytest tests/judge/judge_generate_exercises.py -v -s
"""
import json
import os
import yaml
import pytest

from tests.judge.utils import make_llm, run_metadata, strip_markdown_json, write_results, PROJECT_ROOT


FIXTURE_PATH = os.path.join(PROJECT_ROOT, "tests", "fixtures", "generate_exercises_cases.json")


def load_cases() -> list[dict]:
    with open(FIXTURE_PATH, encoding="utf-8") as f:
        return json.load(f)


def _load_taxonomy_tags() -> set[str]:
    path = os.path.join(PROJECT_ROOT, "lang", "maps", "taxonomy", "german_taxonomy_v1.yaml")
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return set(data["tags"].keys())


_TAXONOMY_TAGS = _load_taxonomy_tags()


JUDGE_PROMPT = """\
You are evaluating a set of German grammar exercises generated for a learner.

Topic: "{topic}"
Target level: {level}

--- PRODUCED EXERCISES (JSON) ---
{exercises_json}

--- EVALUATION ---
For the set as a whole, check:
1. FACTUAL CORRECTNESS — is each correct_answer actually correct German for its
   prompt? Are fill_in_the_blank / multiple_choice / true_false answers
   unambiguous? This is the most important check — a well-formatted exercise
   with a wrong correct_answer must FAIL.
2. TOPIC RELEVANCE — does each exercise actually target "{topic}" (not drift
   into an unrelated grammar point)?
3. ERROR_TAG FIT — does each exercise's error_tag plausibly match the
   grammatical phenomenon being tested?
4. LEVEL FIT — are the exercises reasonably appropriate for a {level} learner?

Rules:
- PASS: all exercises factually correct, on-topic, and reasonably tagged.
- PARTIAL: one exercise has a minor issue (borderline tag, slightly off-level)
  but nothing is factually wrong.
- FAIL: any exercise's correct_answer is factually wrong, or exercises clearly
  drift off-topic.

Return JSON only. No markdown.
{{
  "verdict": "PASS" | "PARTIAL" | "FAIL",
  "score": <float 0.0-1.0>,
  "reasoning": "<one sentence>",
  "issues": ["<specific problem with a specific exercise, if any>"]
}}"""


def _judge(judge_llm, case: dict, exercises: list[dict]) -> dict:
    from llm.base import LLMMessage

    prompt = JUDGE_PROMPT.format(
        topic=case["topic"],
        level=case["level"].upper(),
        exercises_json=json.dumps(exercises, ensure_ascii=False, indent=2),
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
    path = write_results(records, "judge_generate_exercises", metadata=run_metadata())
    print(f"\nResults written to: {path}")


@pytest.mark.judge
@pytest.mark.parametrize("case", load_cases(), ids=[c["id"] for c in load_cases()])
def test_generate_exercises(executor_llm, judge_llm, results_collector, case):
    from skills.generate_exercises.skill import GenerateExercisesSkill
    from skills.protocols import SkillInput

    skill = GenerateExercisesSkill()
    out = skill.run(
        SkillInput(
            user_id="judge",
            level=case["level"],
            parameters={
                "topic": case["topic"],
                "language": case["language"],
                "exercise_type": case["exercise_type"],
                "exercise_count": case["exercise_count"],
            },
        ),
        executor_llm,
    )

    assert out.success, f"[{case['id']}] skill call failed: {out.metadata.get('error')}"
    exercises = out.metadata["exercises"]
    assert exercises, f"[{case['id']}] no exercises produced"

    # --- Structural checks (no LLM) — regression guard on the skill's own contract ---
    from lang.loader import get_exercise_types
    exercise_types_map = get_exercise_types(case["language"])
    for ex in exercises:
        assert ex["error_tag"] in _TAXONOMY_TAGS, (
            f"[{case['id']}] invalid error_tag slipped through: '{ex['error_tag']}'"
        )
        expected_grading = exercise_types_map.grading_for(ex["exercise_type"])
        assert expected_grading is not None, (
            f"[{case['id']}] unknown exercise_type slipped through: '{ex['exercise_type']}'"
        )
        assert ex["grading"] == expected_grading, (
            f"[{case['id']}] wrong grading for {ex['exercise_type']}"
        )

    try:
        verdict = _judge(judge_llm, case, exercises)
    except Exception as e:
        verdict = {"verdict": "ERROR", "score": 0.0, "reasoning": str(e), "issues": []}

    record = {
        "id": case["id"],
        "description": case["description"],
        "topic": case["topic"],
        "level": case["level"],
        "requested_count": case["exercise_count"],
        "produced_count": len(exercises),
        "exercises": exercises,
        "verdict": verdict.get("verdict"),
        "score": verdict.get("score"),
        "reasoning": verdict.get("reasoning"),
        "issues": verdict.get("issues", []),
        "judge_prompt": verdict.get("judge_prompt", ""),
    }
    results_collector.append(record)

    print(f"\n[{case['id']}] {case['description']}")
    print(f"  requested={case['exercise_count']} produced={len(exercises)}")
    print(f"  types: {[(e['exercise_type'], e['grading']) for e in exercises]}")
    print(f"  verdict   : {verdict.get('verdict')}  score={verdict.get('score')}")
    print(f"  reasoning : {verdict.get('reasoning')}")
    if verdict.get("issues"):
        print(f"  issues    : {verdict['issues']}")

    assert verdict.get("verdict") in ("PASS", "PARTIAL"), (
        f"[{case['id']}] FAIL — {verdict.get('reasoning')}\n"
        f"  issues: {verdict.get('issues', [])}\n"
        f"  exercises: {json.dumps(exercises, ensure_ascii=False)}"
    )
