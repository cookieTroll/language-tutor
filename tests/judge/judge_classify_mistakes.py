"""
Judge: ClassifyMistakesSkill (Step 2)

Injects fixture fragments as raw_mistakes (isolates classify from detect).
Judges whether the produced error_tag matches the expected taxonomy tag.

Run:
    pytest tests/judge/judge_classify_mistakes.py -v -s
    LTUT_CONFIG=config.test.yaml pytest tests/judge/judge_classify_mistakes.py -v -s
"""
import json
import os
import yaml
import pytest

from tests.judge.utils import load_cases, make_llm, strip_markdown_json, write_results, PROJECT_ROOT


def _load_taxonomy():
    path = os.path.join(PROJECT_ROOT, "lang", "maps", "taxonomy", "german_taxonomy_v1.yaml")
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    tags = data["tags"]
    text = "\n".join(f"  {tag}: {desc}" for tag, desc in tags.items())
    return text, set(tags.keys())


_TAXONOMY, _TAXONOMY_TAGS = _load_taxonomy()


JUDGE_PROMPT = """\
You are evaluating a German grammar mistake classifier (Step 2 of a writing pipeline).
This step assigns each detected fragment an error_tag from the taxonomy and a minimal correction.

Taxonomy:
{taxonomy}

Student text: {user_text}

Expected classifications (fragment → taxonomy tag):
{expected}

Produced classifications (fragment → error_tag → correction):
{produced}

Evaluate:
1. Does each produced error_tag match the expected taxonomy tag?
   Accept close synonyms within the taxonomy if the linguistic phenomenon is the same.
2. Is the correction minimal and accurate for the fragment?

Rules:
- PASS: all tags correct, corrections are plausible.
- PARTIAL: most tags correct, one minor mismatch or questionable correction.
- FAIL: wrong tags on the majority, or taxonomy tags completely missing.
- Score 0.0 to 1.0.

Return JSON only:
{{
  "verdict": "PASS" | "PARTIAL" | "FAIL",
  "score": <float 0.0-1.0>,
  "reasoning": "<one sentence>",
  "wrong_tags": ["<fragment>: expected X, got Y", ...],
  "correction_issues": ["<fragment>: <problem>", ...]
}}"""


def _judge(judge_llm, case: dict, produced: list[dict]) -> dict:
    from llm.base import LLMMessage

    expected = [
        {"fragment": m["fragment"], "expected_tag": m["error_tag"]}
        for m in case["expected_mistakes"]
    ]
    prompt = JUDGE_PROMPT.format(
        taxonomy=_TAXONOMY,
        user_text=case["user_text"],
        expected=json.dumps(expected, ensure_ascii=False),
        produced=json.dumps(produced, ensure_ascii=False) if produced else "none",
    )
    response = judge_llm.complete([LLMMessage(role="user", content=prompt)], temperature=0.0)
    result = json.loads(strip_markdown_json(response.text.strip()))
    result["judge_prompt"] = prompt
    return result


@pytest.fixture(scope="session", autouse=True)
def verify_fixture_labels():
    """Fail fast if any fixture error_tag is not in the taxonomy."""
    cases = load_cases()
    unknown = [
        f"{c['id']}: '{m['error_tag']}'"
        for c in cases
        for m in c["expected_mistakes"]
        if m["error_tag"] not in _TAXONOMY_TAGS
    ]
    assert not unknown, (
        "Fixture labels not in taxonomy — align pipeline_cases.json with "
        f"german_taxonomy_v1.yaml:\n  " + "\n  ".join(unknown)
    )


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
    path = write_results(records, "judge_classifier")
    print(f"\nResults written to: {path}")


@pytest.mark.judge
@pytest.mark.parametrize("case", load_cases(), ids=[c["id"] for c in load_cases()])
def test_classify_mistakes(executor_llm, judge_llm, results_collector, case):
    from skills.classify_mistakes.skill import ClassifyMistakesSkill
    from skills.protocols import SkillInput

    if not case["expected_mistakes"]:
        pytest.skip("No mistakes to classify")

    # Inject fixture fragments as raw_mistakes — isolates this step from detect
    raw_mistakes = [
        {"fragment": m["fragment"], "error_type_hint": m["error_tag"].replace("_", " ")}
        for m in case["expected_mistakes"]
    ]

    skill = ClassifyMistakesSkill()
    out = skill.run(
        SkillInput(
            user_id="judge",
            level=case["level"],
            parameters={
                "raw_mistakes": raw_mistakes,
                "language": case["language"],
            },
        ),
        executor_llm,
    )
    produced = out.metadata.get("classified_mistakes", [])

    try:
        verdict = _judge(judge_llm, case, produced)
    except Exception as e:
        verdict = {"verdict": "ERROR", "score": 0.0, "reasoning": str(e), "wrong_tags": [], "correction_issues": []}

    record = {
        "id": case["id"],
        "description": case["description"],
        "user_text": case["user_text"],
        "raw_mistakes_input": raw_mistakes,
        "expected_classifications": [{"fragment": m["fragment"], "error_tag": m["error_tag"]} for m in case["expected_mistakes"]],
        "produced": produced,
        "executor_success": out.success,
        "verdict": verdict.get("verdict"),
        "score": verdict.get("score"),
        "reasoning": verdict.get("reasoning"),
        "wrong_tags": verdict.get("wrong_tags", []),
        "correction_issues": verdict.get("correction_issues", []),
        "judge_prompt": verdict.get("judge_prompt", ""),
    }
    results_collector.append(record)

    print(f"\n[{case['id']}] {case['description']}")
    print(f"  produced  : {[(m['fragment'], m['error_tag']) for m in produced]}")
    print(f"  verdict   : {verdict.get('verdict')}  score={verdict.get('score')}")
    print(f"  reasoning : {verdict.get('reasoning')}")

    assert verdict.get("verdict") in ("PASS", "PARTIAL"), (
        f"[{case['id']}] FAIL — {verdict.get('reasoning')}\n"
        f"  produced : {[(m['fragment'], m['error_tag']) for m in produced]}\n"
        f"  expected : {[(m['fragment'], m['error_tag']) for m in case['expected_mistakes']]}"
    )
