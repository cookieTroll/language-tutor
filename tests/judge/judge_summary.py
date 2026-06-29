"""
Judge: SummariseWritingSessionSkill (Step 6)

Injects fixture explained_mistakes, user_text, and writing_prompt directly.
Judges three dimensions:
  1. Summary quality — covers task completion, length, and relevant dimensions honestly
  2. Tip relevance — near-level tips grounded in actual error_tags; no hallucinated topics
  3. Severity accuracy — fundamental errors at the learner's level rated 'critical';
                         repeated error_tags (systematic gap) rated 'critical'

Run:
    pytest tests/judge/judge_summary.py -v -s
    LTUT_CONFIG=config.test.yaml pytest tests/judge/judge_summary.py -v -s
"""
import json
import os
import pytest

from tests.judge.utils import make_llm, strip_markdown_json, write_results, PROJECT_ROOT


FIXTURE_PATH = os.path.join(PROJECT_ROOT, "tests", "fixtures", "summary_cases.json")


def load_cases() -> list[dict]:
    with open(FIXTURE_PATH, encoding="utf-8") as f:
        return json.load(f)


JUDGE_PROMPT = """\
You are evaluating the output of a German writing session summariser (Step 6 of a pipeline).
It receives: a writing prompt, the student's text, a word count, and a list of classified mistakes.
It produces: a session_summary, per-mistake severity ratings, and forward-looking tips.

--- INPUT ---
Writing prompt: {writing_prompt}
Student text ({word_count} words): {user_text}
Learner level: {level}
Mistake error_tags in input: {error_tags}

--- PRODUCED OUTPUT ---
session_summary: {session_summary}
tips: {tips}
severities: {severities}

--- EVALUATION ---
Assess on THREE dimensions:

1. SUMMARY QUALITY
   - If the text is very short relative to the prompt, the summary MUST flag this explicitly — not praise correctness alone.
   - If the task was not fully completed, the summary must state specifically what was missing.
   - Generic praise ("Great job!", "Well done!") without addressing real shortcomings is a FAIL on this dimension.

2. TIP RELEVANCE
   - Near-level tips must be grounded in the actual error_tags listed in the input, or in clearly observable weaknesses in the text.
   - A tip about a grammar topic NOT evidenced in the mistake list and NOT visible in the text is a hallucination — FAIL on this dimension.
   - Aspirational tips may introduce fitting topics for the next CEFR band — these are acceptable.

3. SEVERITY ACCURACY
   - Fundamental errors that should be mastered well before {level} must be rated "critical".
   - If the same error_tag appears 2 or more times (systematic gap), it must be rated "critical".
   - Rating basic errors "minor" at an inappropriate level is a FAIL on this dimension.

Overall verdict:
- PASS: all three dimensions are good.
- PARTIAL: one dimension has a minor issue (e.g. one vague tip, one borderline severity).
- FAIL: any of — summary ignores obvious shortcomings; tip introduces unrelated grammar topic; fundamental repeated error rated "minor".

Return JSON only:
{{
  "verdict": "PASS" | "PARTIAL" | "FAIL",
  "score": <float 0.0-1.0>,
  "reasoning": "<one sentence covering the key finding>",
  "summary_issues": ["<issue with session_summary if any>"],
  "tip_issues": ["<hallucinated or ungrounded tip>"],
  "severity_issues": ["<fragment: expected critical, got minor/expected>"]
}}"""


def _judge(judge_llm, case: dict, produced: dict) -> dict:
    from llm.base import LLMMessage

    mistakes_out = produced.get("mistakes", [])
    severities = [
        {"fragment": m.get("fragment"), "error_tag": m.get("error_tag"), "severity": m.get("severity")}
        for m in mistakes_out
    ]
    error_tags = list({m["error_tag"] for m in case["explained_mistakes"]}) if case["explained_mistakes"] else []

    prompt = JUDGE_PROMPT.format(
        writing_prompt=case["writing_prompt"],
        user_text=case["user_text"],
        word_count=len(case["user_text"].split()),
        level=case["level"].upper(),
        error_tags=json.dumps(error_tags, ensure_ascii=False),
        session_summary=produced.get("session_summary", ""),
        tips=json.dumps(produced.get("tips", []), ensure_ascii=False),
        severities=json.dumps(severities, ensure_ascii=False),
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
    path = write_results(records, "judge_summary")
    print(f"\nResults written to: {path}")


@pytest.mark.judge
@pytest.mark.parametrize("case", load_cases(), ids=[c["id"] for c in load_cases()])
def test_summarise_writing_session(executor_llm, judge_llm, results_collector, case):
    from skills.summarise_session.writing.skill import SummariseWritingSessionSkill
    from skills.protocols import SkillInput

    skill = SummariseWritingSessionSkill()
    out = skill.run(
        SkillInput(
            user_id="judge",
            level=case["level"],
            parameters={
                "user_text": case["user_text"],
                "explained_mistakes": case["explained_mistakes"],
                "writing_prompt": case["writing_prompt"],
                "min_words": case.get("min_words", 0),
                "text_level_estimate": case.get("text_level_estimate"),
                "language": case["language"],
            },
        ),
        executor_llm,
    )
    produced = {
        "session_summary": out.metadata.get("session_summary", ""),
        "tips": out.metadata.get("tips", []),
        "mistakes": out.metadata.get("mistakes", []),
    }

    try:
        verdict = _judge(judge_llm, case, produced)
    except Exception as e:
        verdict = {
            "verdict": "ERROR", "score": 0.0, "reasoning": str(e),
            "summary_issues": [], "tip_issues": [], "severity_issues": [],
        }

    record = {
        "id": case["id"],
        "description": case["description"],
        "user_text": case["user_text"],
        "writing_prompt": case["writing_prompt"],
        "level": case["level"],
        "explained_mistakes_input": case["explained_mistakes"],
        "produced": produced,
        "executor_success": out.success,
        "verdict": verdict.get("verdict"),
        "score": verdict.get("score"),
        "reasoning": verdict.get("reasoning"),
        "summary_issues": verdict.get("summary_issues", []),
        "tip_issues": verdict.get("tip_issues", []),
        "severity_issues": verdict.get("severity_issues", []),
        "judge_prompt": verdict.get("judge_prompt", ""),
    }
    results_collector.append(record)

    print(f"\n[{case['id']}] {case['description']}")
    print(f"  summary   : {produced['session_summary'][:120]}...")
    print(f"  tips      : {produced['tips']}")
    print(f"  verdict   : {verdict.get('verdict')}  score={verdict.get('score')}")
    print(f"  reasoning : {verdict.get('reasoning')}")
    if verdict.get("summary_issues"):
        print(f"  sum issues: {verdict['summary_issues']}")
    if verdict.get("tip_issues"):
        print(f"  tip issues: {verdict['tip_issues']}")
    if verdict.get("severity_issues"):
        print(f"  sev issues: {verdict['severity_issues']}")

    assert verdict.get("verdict") in ("PASS", "PARTIAL"), (
        f"[{case['id']}] FAIL — {verdict.get('reasoning')}\n"
        f"  summary_issues : {verdict.get('summary_issues', [])}\n"
        f"  tip_issues     : {verdict.get('tip_issues', [])}\n"
        f"  severity_issues: {verdict.get('severity_issues', [])}"
    )
