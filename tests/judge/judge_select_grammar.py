"""
Judge: SelectGrammarSkill

Runs the skill against fixture scenarios (error_frequency + recent_topics) and
judges the topic choice. Two layers of checking:
  1. Structural (plain Python, no LLM): a "major" scope pick must exactly match
     a curated topic in the language's grammar_topics map (never hallucinated),
     and the topic must not repeat one of the recent_topics.
  2. LLM judge: is the scope/topic a sound response to the recurring errors and
     level, and is `reason` grounded in the actual input data?

Run:
    pytest tests/judge/judge_select_grammar.py -v -s
    LTUT_CONFIG=config.test.yaml pytest tests/judge/judge_select_grammar.py -v -s
"""
import json
import os
import yaml
import pytest

from tests.judge.utils import make_llm, run_metadata, strip_markdown_json, write_results, PROJECT_ROOT


FIXTURE_PATH = os.path.join(PROJECT_ROOT, "tests", "fixtures", "select_grammar_cases.json")
TOPICS_PATH = os.path.join(PROJECT_ROOT, "lang", "maps", "grammar_topics", "german_a1_b2.yaml")


def load_cases() -> list[dict]:
    with open(FIXTURE_PATH, encoding="utf-8") as f:
        return json.load(f)


def _load_topics_by_name() -> dict[str, dict]:
    with open(TOPICS_PATH, encoding="utf-8") as f:
        topics = yaml.safe_load(f)
    return {t["topic"]: t for t in topics}


_TOPICS_BY_NAME = _load_topics_by_name()


JUDGE_PROMPT = """\
You are evaluating a German grammar topic selector. It receives a learner's
recurring error tags (with counts), recently covered topics to avoid, and the
learner's level. It picks either a curated "major" topic (syllabus backbone)
or proposes its own "minor" topic when no major topic fits well.

--- INPUT ---
Level: {level}
Recurring errors (error_tag → count): {error_frequency}
Recently covered topics (avoid repeating): {recent_topics}

--- PRODUCED ---
topic: {topic}
difficulty: {difficulty}
scope: {scope}
reason: {reason}
{topic_tags_note}

--- GUIDANCE ---
A well-reasoned pick would target: {dominant_tag_note}

Evaluate:
1. Does the choice sensibly address the dominant recurring error (if any)?
2. Is `reason` grounded in the actual error_frequency / recent_topics data above,
   not generic or hallucinated?
3. Is `difficulty` reasonably close to the learner's level (exact match not required
   if the topic naturally sits at an adjacent level)?
4. If scope is "minor", is that justified (no good major topic fits, e.g. major
   candidates for this tag were already recently covered, or the error is a small/
   idiomatic point)?

Rules:
- PASS: sound topic choice, reason grounded in the data.
- PARTIAL: defensible choice but reason is vague, or difficulty is a bit off.
- FAIL: ignores the dominant recurring error with no justification, reason is
  generic/hallucinated, or scope choice contradicts the guidance with no rationale.

Return JSON only:
{{
  "verdict": "PASS" | "PARTIAL" | "FAIL",
  "score": <float 0.0-1.0>,
  "reasoning": "<one sentence>"
}}"""


def _judge(judge_llm, case: dict, produced: dict) -> dict:
    from llm.base import LLMMessage

    topic_entry = _TOPICS_BY_NAME.get(produced["topic"])
    topic_tags_note = (
        f"(curated related_error_tags for this topic: {topic_entry['related_error_tags']})"
        if topic_entry else "(topic is not in the curated list — proposed ad hoc)"
    )
    dominant_tag = case.get("dominant_tag")
    dominant_tag_note = (
        f"the recurring '{dominant_tag}' error" if dominant_tag else
        "no strong recurring signal yet — any reasonable foundational topic for the level is fine"
    )

    prompt = JUDGE_PROMPT.format(
        level=case["level"].upper(),
        error_frequency=json.dumps(case["error_frequency"]),
        recent_topics=", ".join(case["recent_topics"]) or "(none)",
        topic=produced["topic"],
        difficulty=produced["difficulty"],
        scope=produced["scope"],
        reason=produced["reason"],
        topic_tags_note=topic_tags_note,
        dominant_tag_note=dominant_tag_note,
    )
    response = judge_llm.complete([LLMMessage(role="user", content=prompt)], temperature=0.0)
    text = strip_markdown_json(response.text.strip())
    # Some local judge models append stray text after the JSON object — decode
    # only the leading JSON value and ignore trailing data instead of failing.
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
    path = write_results(records, "judge_select_grammar", metadata=run_metadata())
    print(f"\nResults written to: {path}")


@pytest.mark.judge
@pytest.mark.parametrize("case", load_cases(), ids=[c["id"] for c in load_cases()])
def test_select_grammar(executor_llm, judge_llm, results_collector, case):
    from skills.select_grammar.skill import SelectGrammarSkill
    from skills.protocols import SkillInput

    skill = SelectGrammarSkill()
    out = skill.run(
        SkillInput(
            user_id="judge",
            level=case["level"],
            parameters={
                "language": case["language"],
                "error_frequency": case["error_frequency"],
                "recent_topics": case["recent_topics"],
            },
        ),
        executor_llm,
    )

    assert out.success, f"[{case['id']}] skill call failed: {out.metadata.get('error')}"
    produced = out.metadata

    # --- Structural checks (no LLM) ---
    assert produced["topic"] not in case["recent_topics"], (
        f"[{case['id']}] repeated a recently covered topic: '{produced['topic']}'"
    )
    if produced["scope"] == "major":
        assert produced["topic"] in _TOPICS_BY_NAME, (
            f"[{case['id']}] scope=major but topic is not in the curated grammar_topics "
            f"map (hallucinated): '{produced['topic']}'"
        )

    try:
        verdict = _judge(judge_llm, case, produced)
    except Exception as e:
        verdict = {"verdict": "ERROR", "score": 0.0, "reasoning": str(e)}

    record = {
        "id": case["id"],
        "description": case["description"],
        "level": case["level"],
        "error_frequency": case["error_frequency"],
        "recent_topics": case["recent_topics"],
        "produced": produced,
        "verdict": verdict.get("verdict"),
        "score": verdict.get("score"),
        "reasoning": verdict.get("reasoning"),
        "judge_prompt": verdict.get("judge_prompt", ""),
    }
    results_collector.append(record)

    print(f"\n[{case['id']}] {case['description']}")
    print(f"  produced  : topic='{produced['topic']}' scope={produced['scope']} difficulty={produced['difficulty']}")
    print(f"  reason    : {produced['reason']}")
    print(f"  verdict   : {verdict.get('verdict')}  score={verdict.get('score')}")
    print(f"  reasoning : {verdict.get('reasoning')}")

    assert verdict.get("verdict") in ("PASS", "PARTIAL"), (
        f"[{case['id']}] FAIL — {verdict.get('reasoning')}\n"
        f"  produced: {produced}"
    )
