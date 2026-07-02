"""
Judge: SummarizeWritingHistorySkill

Runs the skill against fixture scenarios and judges whether the produced report is
grounded in the pre-aggregated input (topics, recurring mistake tags, level trend)
without hallucinating data or claiming a trend the input doesn't support.

Run:
    pytest tests/judge/judge_summarize_writing_history.py -v -s
    LTUT_CONFIG=config.test.yaml pytest tests/judge/judge_summarize_writing_history.py -v -s
"""
import json
import os
import pytest

from tests.judge.utils import make_llm, strip_markdown_json, write_results, PROJECT_ROOT


FIXTURE_PATH = os.path.join(PROJECT_ROOT, "tests", "fixtures", "summarize_writing_history_cases.json")


def load_cases() -> list[dict]:
    with open(FIXTURE_PATH, encoding="utf-8") as f:
        return json.load(f)


JUDGE_PROMPT = """\
You are evaluating the output of a language tutor's on-demand writing-history report.
It receives pre-aggregated stats for a window of the learner's writing sessions and
must summarise them in plain language.

--- INPUT ---
Level: {level}
Scope: {scope_label}
Topics covered: {topics}
Recurring mistake tags (tag: count): {recurring_mistakes}
Level trend (oldest to newest): {level_trend}

--- PRODUCED REPORT ---
{history_summary}

--- EVALUATION ---
Assess on THREE dimensions:

1. GROUNDING — every claim in the report must trace back to the input above. No invented
   topics, error tags, or level values.
2. NO OVERCLAIMING — if there's only one level-trend data point (or none), the report must
   NOT claim the level is "improving" or "declining". If recurring_mistakes is empty, the
   report must say there's no clear recurring pattern rather than naming a tag.
3. COVERAGE — the report should touch on topics, recurring mistakes (or their absence),
   and the level trend (or note there isn't enough data), not omit a dimension entirely.

These specific elements should appear (verify they're accurately represented, not just
present as literal text): {must_mention}

Overall verdict:
- PASS: grounded, no overclaiming, reasonable coverage.
- PARTIAL: mostly grounded but missing one dimension, or a mild overclaim.
- FAIL: hallucinated data, or claims a trend/pattern the input doesn't support.

Return JSON only. No markdown.
{{
  "verdict": "PASS" | "PARTIAL" | "FAIL",
  "score": <float 0.0-1.0>,
  "reasoning": "<one sentence covering the key finding>",
  "issues": ["<specific issue if any>"]
}}"""


def _judge(judge_llm, case: dict, history_summary: str) -> dict:
    from llm.base import LLMMessage

    prompt = JUDGE_PROMPT.format(
        level=case["level"].upper(),
        scope_label=case["scope_label"],
        topics=json.dumps(case["topics"]),
        recurring_mistakes=json.dumps(case["recurring_mistakes"]),
        level_trend=json.dumps(case["level_trend"]),
        history_summary=history_summary,
        must_mention=json.dumps(case["must_mention"]),
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
    path = write_results(records, "judge_summarize_writing_history")
    print(f"\nResults written to: {path}")


@pytest.mark.judge
@pytest.mark.parametrize("case", load_cases(), ids=[c["id"] for c in load_cases()])
def test_summarize_writing_history(executor_llm, judge_llm, results_collector, case):
    from skills.summarize_writing_history.skill import SummarizeWritingHistorySkill
    from skills.protocols import SkillInput

    skill = SummarizeWritingHistorySkill()
    out = skill.run(
        SkillInput(
            user_id="judge",
            level=case["level"],
            parameters={
                "language": case["language"],
                "scope_label": case["scope_label"],
                "topics": case["topics"],
                "recurring_mistakes": case["recurring_mistakes"],
                "level_trend": case["level_trend"],
            },
        ),
        executor_llm,
    )

    history_summary = out.metadata.get("history_summary", "")

    try:
        verdict = _judge(judge_llm, case, history_summary)
    except Exception as e:
        verdict = {"verdict": "ERROR", "score": 0.0, "reasoning": str(e), "issues": []}

    record = {
        "id": case["id"],
        "description": case["description"],
        "level": case["level"],
        "history_summary": history_summary,
        "executor_success": out.success,
        "verdict": verdict.get("verdict"),
        "score": verdict.get("score"),
        "reasoning": verdict.get("reasoning"),
        "issues": verdict.get("issues", []),
        "judge_prompt": verdict.get("judge_prompt", ""),
    }
    results_collector.append(record)

    print(f"\n[{case['id']}] {case['description']}")
    print(f"  history_summary : {history_summary}")
    print(f"  verdict         : {verdict.get('verdict')}  score={verdict.get('score')}")
    print(f"  reasoning       : {verdict.get('reasoning')}")
    if verdict.get("issues"):
        print(f"  issues          : {verdict['issues']}")

    assert out.success is True, f"[{case['id']}] skill call failed: {history_summary}"
    assert verdict.get("verdict") in ("PASS", "PARTIAL"), (
        f"[{case['id']}] FAIL — {verdict.get('reasoning')}\n"
        f"  issues : {verdict.get('issues', [])}"
    )
