"""
Judge: SummarizeProgressSkill

Runs the skill against fixture scenarios and judges two dimensions:
  1. Module correctness — weakest_module matches what the data clearly implies
  2. Reason quality — recommendation_reason is grounded in the aggregate data

Run:
    pytest tests/judge/judge_summarize_progress.py -v -s
    LTUT_CONFIG=config.test.yaml pytest tests/judge/judge_summarize_progress.py -v -s
"""
import json
import os
import pytest

from tests.judge.utils import make_llm, strip_markdown_json, write_results, PROJECT_ROOT


FIXTURE_PATH = os.path.join(PROJECT_ROOT, "tests", "fixtures", "progress_cases.json")


def load_cases() -> list[dict]:
    with open(FIXTURE_PATH, encoding="utf-8") as f:
        return json.load(f)


JUDGE_PROMPT = """\
You are evaluating the output of a language tutor progress summariser.
It receives a learner's session history aggregate and recommends the next module to focus on.

--- INPUT AGGREGATE ---
Level: {level}
Available modules: {modules}
Sessions by module: {sessions_by_module}
Days since last session by module: {days_since_module}
Total minutes by module: {total_time_by_module}
Recurring error tags (freq >= 2): {recurring_errors}
Recent writing topics: {recent_topics}
Vocab flags: {vocab_flag_count}

--- PRODUCED OUTPUT ---
weakest_module: {weakest_module}
recommendation_reason: {recommendation_reason}

--- EXPECTED ---
A well-reasoned recommendation would point to: {expected_module}

--- EVALUATION ---
Assess on TWO dimensions:

1. MODULE CORRECTNESS
   - Does weakest_module match what the data clearly implies?
   - A module with zero sessions should be recommended over an active one.
   - A module that is stale (last session >14 days ago) should be preferred over a very recent one.
   - Recurring grammar errors are a strong signal to recommend grammar.
   - Minor deviations are acceptable if the reason is sound.

2. REASON QUALITY
   - Is recommendation_reason grounded in the actual data above?
   - Does it mention specific evidence (session counts, error tags, days since last session)?
   - Generic reasons ("you should practice more") with no data reference are a FAIL.

Overall verdict:
- PASS: module is correct and reason is grounded.
- PARTIAL: module is defensible but reason is vague, or minor data mismatch.
- FAIL: module contradicts the clear data signal, or reason is hallucinated/generic.

Return JSON only. No markdown.
{{
  "verdict": "PASS" | "PARTIAL" | "FAIL",
  "score": <float 0.0-1.0>,
  "reasoning": "<one sentence covering the key finding>",
  "module_issues": ["<issue with weakest_module if any>"],
  "reason_issues": ["<issue with recommendation_reason if any>"]
}}"""


def _judge(judge_llm, case: dict, produced: dict) -> dict:
    from llm.base import LLMMessage

    agg = case["aggregate"]
    prompt = JUDGE_PROMPT.format(
        level=case["level"].upper(),
        modules=", ".join(case["modules"]),
        sessions_by_module=json.dumps(agg["sessions_by_module"]),
        days_since_module=json.dumps(agg["days_since_module"]),
        total_time_by_module=json.dumps(agg["total_time_by_module"]),
        recurring_errors=json.dumps(agg["recurring_errors"]),
        recent_topics=json.dumps(agg["recent_topics"]),
        vocab_flag_count=agg["vocab_flag_count"],
        weakest_module=produced.get("weakest_module", ""),
        recommendation_reason=produced.get("recommendation_reason", ""),
        expected_module=case["expected_module"],
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
    path = write_results(records, "judge_summarize_progress")
    print(f"\nResults written to: {path}")


@pytest.mark.judge
@pytest.mark.parametrize("case", load_cases(), ids=[c["id"] for c in load_cases()])
def test_summarize_progress(executor_llm, judge_llm, results_collector, case):
    from skills.summarize_progress.skill import SummarizeProgressSkill
    from skills.protocols import SkillInput

    skill = SummarizeProgressSkill()
    out = skill.run(
        SkillInput(
            user_id="judge",
            level=case["level"],
            parameters={
                "aggregate": case["aggregate"],
                "modules": case["modules"],
            },
        ),
        executor_llm,
    )

    produced = {
        "weakest_module": out.metadata.get("weakest_module", ""),
        "recommendation_reason": out.metadata.get("recommendation_reason", ""),
    }

    try:
        verdict = _judge(judge_llm, case, produced)
    except Exception as e:
        verdict = {
            "verdict": "ERROR", "score": 0.0, "reasoning": str(e),
            "module_issues": [], "reason_issues": [],
        }

    record = {
        "id": case["id"],
        "description": case["description"],
        "level": case["level"],
        "aggregate": case["aggregate"],
        "expected_module": case["expected_module"],
        "produced": produced,
        "executor_success": out.success,
        "verdict": verdict.get("verdict"),
        "score": verdict.get("score"),
        "reasoning": verdict.get("reasoning"),
        "module_issues": verdict.get("module_issues", []),
        "reason_issues": verdict.get("reason_issues", []),
        "judge_prompt": verdict.get("judge_prompt", ""),
    }
    results_collector.append(record)

    print(f"\n[{case['id']}] {case['description']}")
    print(f"  weakest_module : {produced['weakest_module']}")
    print(f"  reason         : {produced['recommendation_reason']}")
    print(f"  verdict        : {verdict.get('verdict')}  score={verdict.get('score')}")
    print(f"  reasoning      : {verdict.get('reasoning')}")
    if verdict.get("module_issues"):
        print(f"  module issues  : {verdict['module_issues']}")
    if verdict.get("reason_issues"):
        print(f"  reason issues  : {verdict['reason_issues']}")

    assert verdict.get("verdict") in ("PASS", "PARTIAL"), (
        f"[{case['id']}] FAIL — {verdict.get('reasoning')}\n"
        f"  module_issues : {verdict.get('module_issues', [])}\n"
        f"  reason_issues : {verdict.get('reason_issues', [])}"
    )
