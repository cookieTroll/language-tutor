"""
Unit tests for Layer 2a grammar skills. All LLM calls are mocked — no live network access.
"""
import json
from unittest.mock import MagicMock

from llm.base import BaseLLM, LLMResponse
from skills.protocols import SkillInput


def make_llm(responses: list[str]) -> MagicMock:
    """Create a mock BaseLLM whose .complete() returns each response in order."""
    llm = MagicMock(spec=BaseLLM)
    llm.config = MagicMock()
    llm.config.max_skill_retries = 3
    llm.config.show_incomplete_responses = False
    llm.config.show_cut_by_limit_tag = True
    llm.complete.side_effect = [LLMResponse(text=t, model="test-model") for t in responses]
    return llm


def make_input(level: str = "b1", **params) -> SkillInput:
    return SkillInput(user_id="user1", level=level, parameters=params)


# ---------------------------------------------------------------------------
# SelectGrammarSkill
# ---------------------------------------------------------------------------

class TestSelectGrammarSkill:

    def test_selects_major_topic(self):
        from skills.select_grammar.skill import SelectGrammarSkill
        payload = json.dumps({
            "topic": "Dative case — prepositions",
            "difficulty": "b1",
            "scope": "major",
            "reason": "noun_declension error appeared 4 times",
        })
        llm = make_llm([payload])

        skill = SelectGrammarSkill()
        out = skill.run(
            make_input(
                language="german",
                error_frequency={"noun_declension": 4},
                recent_topics=["Present tense — regular verbs"],
            ),
            llm,
        )

        assert out.success is True
        assert out.metadata["topic"] == "Dative case — prepositions"
        assert out.metadata["difficulty"] == "b1"
        assert out.metadata["scope"] == "major"
        assert out.metadata["reason"]

        # Curated topics for German must have reached the prompt.
        prompt_text = llm.complete.call_args_list[0].args[0][0].content
        assert "Present tense — regular verbs" in prompt_text
        assert "verb_conjugation" in prompt_text

    def test_suggested_focus_reaches_prompt(self):
        """The orchestrator's recommended focus must reach the LLM prompt so
        the module actually honors what the confirm screen suggested, instead
        of re-deriving a topic independently."""
        from skills.select_grammar.skill import SelectGrammarSkill
        payload = json.dumps({
            "topic": "Dative case — prepositions",
            "difficulty": "b1",
            "scope": "major",
            "reason": "matches suggested focus",
        })
        llm = make_llm([payload])

        skill = SelectGrammarSkill()
        skill.run(
            make_input(
                language="german",
                error_frequency={"noun_declension": 4},
                recent_topics=[],
                suggested_focus="noun_declension",
            ),
            llm,
        )

        prompt_text = llm.complete.call_args_list[0].args[0][0].content
        assert "noun_declension" in prompt_text

    def test_missing_suggested_focus_defaults_to_none_placeholder(self):
        from skills.select_grammar.skill import SelectGrammarSkill
        payload = json.dumps({
            "topic": "Basic word order", "difficulty": "a1", "scope": "minor", "reason": "x",
        })
        llm = make_llm([payload])

        skill = SelectGrammarSkill()
        out = skill.run(make_input(language="german", error_frequency={}, recent_topics=[]), llm)

        assert out.success is True
        prompt_text = llm.complete.call_args_list[0].args[0][0].content
        assert "(none)" in prompt_text

    def test_selects_minor_topic_when_no_major_fits(self):
        from skills.select_grammar.skill import SelectGrammarSkill
        payload = json.dumps({
            "topic": "sondern vs. aber",
            "difficulty": "b1",
            "scope": "minor",
            "reason": "connector confusion is idiomatic, not covered by a major topic",
        })
        llm = make_llm([payload])

        skill = SelectGrammarSkill()
        out = skill.run(
            make_input(language="german", error_frequency={"other": 3}, recent_topics=[]),
            llm,
        )

        assert out.success is True
        assert out.metadata["scope"] == "minor"

    def test_unknown_language_falls_back_gracefully(self):
        """No grammar_topics map for the language must not crash — LLM still consulted."""
        from skills.select_grammar.skill import SelectGrammarSkill
        payload = json.dumps({
            "topic": "Basic word order",
            "difficulty": "a1",
            "scope": "minor",
            "reason": "no curated topics available",
        })
        llm = make_llm([payload])

        skill = SelectGrammarSkill()
        out = skill.run(
            make_input(language="klingon", error_frequency={}, recent_topics=[]),
            llm,
        )

        assert out.success is True
        prompt_text = llm.complete.call_args_list[0].args[0][0].content
        assert "(none available)" in prompt_text

    def test_rejects_invalid_difficulty_triggers_retry(self):
        from skills.select_grammar.skill import SelectGrammarSkill
        bad = json.dumps({
            "topic": "Dative case", "difficulty": "intermediate", "scope": "major", "reason": "x",
        })
        good = json.dumps({
            "topic": "Dative case", "difficulty": "b1", "scope": "major", "reason": "x",
        })
        llm = make_llm([bad, good])

        skill = SelectGrammarSkill()
        out = skill.run(make_input(language="german", error_frequency={}, recent_topics=[]), llm)

        assert out.success is True
        assert out.metadata["difficulty"] == "b1"
        assert llm.complete.call_count == 2

    def test_rejects_invalid_scope_triggers_retry(self):
        from skills.select_grammar.skill import SelectGrammarSkill
        bad = json.dumps({
            "topic": "Dative case", "difficulty": "b1", "scope": "syllabus", "reason": "x",
        })
        good = json.dumps({
            "topic": "Dative case", "difficulty": "b1", "scope": "major", "reason": "x",
        })
        llm = make_llm([bad, good])

        skill = SelectGrammarSkill()
        out = skill.run(make_input(language="german", error_frequency={}, recent_topics=[]), llm)

        assert out.success is True
        assert out.metadata["scope"] == "major"
        assert llm.complete.call_count == 2

    def test_missing_key_fails_after_retries_exhausted(self):
        from skills.select_grammar.skill import SelectGrammarSkill
        bad = json.dumps({"topic": "Dative case", "difficulty": "b1"})  # missing scope/reason
        llm = make_llm([bad, bad, bad])

        skill = SelectGrammarSkill()
        out = skill.run(make_input(language="german", error_frequency={}, recent_topics=[]), llm)

        assert out.success is False
        assert "error" in out.metadata


# ---------------------------------------------------------------------------
# resolve_manual_topic (manual override — no LLM call)
# ---------------------------------------------------------------------------

class TestResolveManualTopic:

    def test_exact_match_resolves_as_major(self):
        from skills.select_grammar.skill import resolve_manual_topic
        result = resolve_manual_topic(
            "Dative case — indirect objects and personal pronouns", level="a2", language="german",
        )
        assert result["scope"] == "major"
        assert result["difficulty"] == "a2"
        assert result["topic"] == "Dative case — indirect objects and personal pronouns"

    def test_case_insensitive_match_resolves_as_major(self):
        from skills.select_grammar.skill import resolve_manual_topic
        result = resolve_manual_topic(
            "  present tense — sein AND haben  ", level="a1", language="german",
        )
        assert result["scope"] == "major"
        assert result["topic"] == "Present tense — sein and haben"
        assert result["difficulty"] == "a1"

    def test_no_match_falls_back_to_minor_at_stated_level(self):
        from skills.select_grammar.skill import resolve_manual_topic
        result = resolve_manual_topic("Sondern vs aber", level="b1", language="german")
        assert result["scope"] == "minor"
        assert result["topic"] == "Sondern vs aber"
        assert result["difficulty"] == "b1"

    def test_unknown_language_falls_back_to_minor(self):
        from skills.select_grammar.skill import resolve_manual_topic
        result = resolve_manual_topic("Some topic", level="a1", language="klingon")
        assert result["scope"] == "minor"
        assert result["difficulty"] == "a1"


# ---------------------------------------------------------------------------
# DumpGrammarSkill
# ---------------------------------------------------------------------------

class TestDumpGrammarSkill:

    def test_produces_markdown_explanation(self):
        from skills.dump_grammar.skill import DumpGrammarSkill
        explanation = "# Dative case\n\n## Rule\n...\n\n| Case | Article |\n|---|---|"
        llm = make_llm([explanation])

        skill = DumpGrammarSkill()
        out = skill.run(
            make_input(level="b1", topic="Dative case — prepositions", language="german"), llm,
        )

        assert out.success is True
        assert out.metadata["explanation"] == explanation
        prompt_text = llm.complete.call_args_list[0].args[0][0].content
        assert "Dative case — prepositions" in prompt_text
        assert "B1" in prompt_text

    def test_empty_topic_short_circuits_without_llm_call(self):
        from skills.dump_grammar.skill import DumpGrammarSkill
        llm = make_llm([])

        skill = DumpGrammarSkill()
        out = skill.run(make_input(level="b1", topic="   ", language="german"), llm)

        assert out.success is False
        assert out.metadata["explanation"] == ""
        llm.complete.assert_not_called()

    def test_truncated_response_appends_tag(self):
        from skills.dump_grammar.skill import DumpGrammarSkill
        llm = MagicMock(spec=BaseLLM)
        llm.config = MagicMock()
        llm.config.show_cut_by_limit_tag = True
        llm.complete.return_value = LLMResponse(text="Partial explanation...", model="test-model", truncated=True)

        skill = DumpGrammarSkill()
        out = skill.run(make_input(level="b1", topic="Dative case", language="german"), llm)

        assert out.success is True
        assert out.metadata["explanation"].endswith("[TRUNCATED BY LIMIT]")

    def test_empty_response_fails(self):
        from skills.dump_grammar.skill import DumpGrammarSkill
        llm = make_llm(["   "])

        skill = DumpGrammarSkill()
        out = skill.run(make_input(level="b1", topic="Dative case", language="german"), llm)

        assert out.success is False
        assert "error" in out.metadata

    def test_llm_exception_fails_gracefully(self):
        from skills.dump_grammar.skill import DumpGrammarSkill
        llm = MagicMock(spec=BaseLLM)
        llm.config = MagicMock()
        llm.complete.side_effect = RuntimeError("connection refused")

        skill = DumpGrammarSkill()
        out = skill.run(make_input(level="b1", topic="Dative case", language="german"), llm)

        assert out.success is False
        assert "connection refused" in out.metadata["error"]

    def test_curated_topic_scope_notes_reach_prompt(self):
        """The A2 Präteritum topic is deliberately narrow (haben/sein/modals
        only) — its curated out_of_scope must reach the prompt so the
        explanation doesn't drift into irregular main-verb Präteritum, which
        generate_exercises might then test without ever having been explained."""
        from skills.dump_grammar.skill import DumpGrammarSkill
        llm = make_llm(["# Präteritum\n..."])

        skill = DumpGrammarSkill()
        skill.run(
            make_input(level="a2", topic="Präteritum — haben, sein, and modal verbs", language="german"),
            llm,
        )

        prompt_text = llm.complete.call_args_list[0].args[0][0].content
        assert "Out of scope" in prompt_text
        assert "gehen→ging" in prompt_text

    def test_uncurated_topic_gets_generic_scope_fallback(self):
        from skills.dump_grammar.skill import DumpGrammarSkill
        llm = make_llm(["explanation"])

        skill = DumpGrammarSkill()
        skill.run(
            make_input(level="b1", topic="sondern vs. aber", language="german"), llm,
        )

        prompt_text = llm.complete.call_args_list[0].args[0][0].content
        assert "hard scope boundary" in prompt_text


# ---------------------------------------------------------------------------
# GenerateExercisesSkill
# ---------------------------------------------------------------------------

def _exercise(**overrides) -> dict:
    base = {
        "prompt": "Ich fahre ___ meinem Freund. (with)",
        "type": "fill_in_the_blank",
        "correct_answer": "mit",
        "accepted_answers": [],
        "error_tag": "noun_declension",
        "distractor_hint": "Students often confuse 'mit' + accusative",
    }
    base.update(overrides)
    return base


class TestGenerateExercisesSkill:

    def test_wrong_type_triggers_retry(self):
        """The exercise type is now fixed by the caller (modules/grammar/agent.py
        picks it in code, not the LLM) — a model that drifts to a different type,
        or mixes types, is a hard mismatch that triggers a retry instead of being
        silently filtered down to whatever type happened to come first."""
        from skills.generate_exercises.skill import GenerateExercisesSkill
        bad = json.dumps({"exercises": [
            _exercise(type="fill_in_the_blank", prompt="p1", correct_answer="a1"),
            _exercise(type="word_order", prompt="p2", correct_answer="a2", error_tag="word_order"),
        ]})
        good = json.dumps({"exercises": [
            _exercise(type="fill_in_the_blank", prompt="p1", correct_answer="a1"),
            _exercise(type="fill_in_the_blank", prompt="p3", correct_answer="a3"),
        ]})
        llm = make_llm([bad, good])

        skill = GenerateExercisesSkill()
        out = skill.run(
            make_input(
                level="a1", topic="Dative case", language="german",
                exercise_type="fill_in_the_blank", exercise_count=2,
            ),
            llm,
        )

        assert out.success is True
        types = [ex["exercise_type"] for ex in out.metadata["exercises"]]
        prompts = [ex["prompt"] for ex in out.metadata["exercises"]]
        assert types == ["fill_in_the_blank", "fill_in_the_blank"]
        assert prompts == ["p1", "p3"]
        assert llm.complete.call_count == 2

    def test_count_mismatch_triggers_retry(self):
        """Requesting N exercises must produce exactly N of the given type — a
        short batch (all matching type, but too few) is now a hard retry trigger,
        not a silently-accepted partial batch."""
        from skills.generate_exercises.skill import GenerateExercisesSkill
        short = json.dumps({"exercises": [_exercise(prompt="p1", correct_answer="a1")]})
        full = json.dumps({"exercises": [
            _exercise(prompt="p1", correct_answer="a1"),
            _exercise(prompt="p2", correct_answer="a2"),
        ]})
        llm = make_llm([short, full])

        skill = GenerateExercisesSkill()
        out = skill.run(
            make_input(
                level="a1", topic="Dative case", language="german",
                exercise_type="fill_in_the_blank", exercise_count=2,
            ),
            llm,
        )

        assert out.success is True
        assert len(out.metadata["exercises"]) == 2
        assert llm.complete.call_count == 2

    def test_grading_derived_from_exercise_type_map(self):
        """grading is derived from lang/maps/exercise_types, not trusted from the
        model — verified here for an llm-graded type (exact-type derivation is
        already exercised by the fill_in_the_blank cases throughout this file)."""
        from skills.generate_exercises.skill import GenerateExercisesSkill
        payload = json.dumps({"exercises": [
            _exercise(
                type="word_order", error_tag="word_order",
                prompt="Reorder: heute / ich / Deutsch / lerne",
                correct_answer="Heute lerne ich Deutsch.",
            ),
        ]})
        llm = make_llm([payload])

        skill = GenerateExercisesSkill()
        out = skill.run(
            make_input(
                level="a1", topic="Dative case", language="german",
                exercise_type="word_order", exercise_count=1,
            ),
            llm,
        )

        assert out.success is True
        exercises = out.metadata["exercises"]
        assert len(exercises) == 1
        assert exercises[0]["exercise_type"] == "word_order"
        assert exercises[0]["grading"] == "llm"

    def test_empty_topic_short_circuits_without_llm_call(self):
        from skills.generate_exercises.skill import GenerateExercisesSkill
        llm = make_llm([])

        skill = GenerateExercisesSkill()
        out = skill.run(make_input(level="a1", topic="  ", language="german"), llm)

        assert out.success is False
        assert out.metadata["exercises"] == []
        llm.complete.assert_not_called()

    def test_curated_topic_scope_notes_reach_prompt(self):
        """Mirrors the dump_grammar scope test — generate_exercises must see
        the same curated in_scope/out_of_scope so it doesn't test irregular
        main verbs on a topic scoped to haben/sein/modals only."""
        from skills.generate_exercises.skill import GenerateExercisesSkill
        payload = json.dumps({"exercises": [_exercise(
            prompt="Ich ___ (können) das nicht.", correct_answer="konnte", error_tag="verb_tense",
        )]})
        llm = make_llm([payload])

        skill = GenerateExercisesSkill()
        skill.run(
            make_input(
                level="a2", topic="Präteritum — haben, sein, and modal verbs", language="german",
                exercise_type="fill_in_the_blank", exercise_count=1,
            ),
            llm,
        )

        prompt_text = llm.complete.call_args_list[0].args[0][0].content
        assert "Out of scope" in prompt_text
        assert "gehen→ging" in prompt_text

    def test_uncurated_topic_gets_generic_scope_fallback(self):
        from skills.generate_exercises.skill import GenerateExercisesSkill
        payload = json.dumps({"exercises": [_exercise()]})
        llm = make_llm([payload])

        skill = GenerateExercisesSkill()
        skill.run(
            make_input(
                level="b1", topic="sondern vs. aber", language="german",
                exercise_type="fill_in_the_blank", exercise_count=1,
            ),
            llm,
        )

        prompt_text = llm.complete.call_args_list[0].args[0][0].content
        assert "hard scope boundary" in prompt_text

    def test_unrecognized_language_falls_back_to_default_taxonomy(self):
        """No language config means get_taxonomy falls back to the default map
        (grammar/vocabulary/spelling/other) — the skill must still call the LLM
        and validate tags against that fallback, not fail outright."""
        from skills.generate_exercises.skill import GenerateExercisesSkill
        payload = json.dumps({"exercises": [_exercise(error_tag="vocabulary")]})
        llm = make_llm([payload])

        skill = GenerateExercisesSkill()
        out = skill.run(
            make_input(
                level="a1", topic="Dative case", language="klingon",
                exercise_type="fill_in_the_blank", exercise_count=1,
            ),
            llm,
        )

        assert out.success is True
        assert out.metadata["exercises"][0]["error_tag"] == "vocabulary"

    def test_invalid_error_tag_triggers_retry(self):
        from skills.generate_exercises.skill import GenerateExercisesSkill
        bad = json.dumps({"exercises": [_exercise(error_tag="made_up_tag")]})
        good = json.dumps({"exercises": [_exercise(error_tag="noun_declension")]})
        llm = make_llm([bad, good])

        skill = GenerateExercisesSkill()
        out = skill.run(
            make_input(
                level="a1", topic="Dative case", language="german",
                exercise_type="fill_in_the_blank", exercise_count=1,
            ),
            llm,
        )

        assert out.success is True
        assert out.metadata["exercises"][0]["error_tag"] == "noun_declension"
        assert llm.complete.call_count == 2

    def test_null_error_tag_triggers_retry(self):
        """Model occasionally emits error_tag: null on hard topics — must retry
        with a clear message, not silently coerce None to the string 'None'."""
        from skills.generate_exercises.skill import GenerateExercisesSkill
        bad = json.dumps({"exercises": [_exercise(error_tag=None)]})
        good = json.dumps({"exercises": [_exercise(error_tag="noun_declension")]})
        llm = make_llm([bad, good])

        skill = GenerateExercisesSkill()
        out = skill.run(
            make_input(
                level="a1", topic="Dative case", language="german",
                exercise_type="fill_in_the_blank", exercise_count=1,
            ),
            llm,
        )

        assert out.success is True
        assert out.metadata["exercises"][0]["error_tag"] == "noun_declension"
        assert llm.complete.call_count == 2

    def test_invalid_exercise_type_triggers_retry(self):
        from skills.generate_exercises.skill import GenerateExercisesSkill
        bad = json.dumps({"exercises": [_exercise(type="matching")]})
        good = json.dumps({"exercises": [_exercise(type="fill_in_the_blank")]})
        llm = make_llm([bad, good])

        skill = GenerateExercisesSkill()
        out = skill.run(
            make_input(
                level="a1", topic="Dative case", language="german",
                exercise_type="fill_in_the_blank", exercise_count=1,
            ),
            llm,
        )

        assert out.success is True
        assert out.metadata["exercises"][0]["exercise_type"] == "fill_in_the_blank"
        assert llm.complete.call_count == 2

    def test_no_exercises_returned_triggers_retry(self):
        from skills.generate_exercises.skill import GenerateExercisesSkill
        empty = json.dumps({"exercises": []})
        good = json.dumps({"exercises": [_exercise()]})
        llm = make_llm([empty, good])

        skill = GenerateExercisesSkill()
        out = skill.run(
            make_input(
                level="a1", topic="Dative case", language="german",
                exercise_type="fill_in_the_blank", exercise_count=1,
            ),
            llm,
        )

        assert out.success is True
        assert len(out.metadata["exercises"]) == 1
        assert llm.complete.call_count == 2

    def test_missing_accepted_answers_defaults_to_empty_list(self):
        from skills.generate_exercises.skill import GenerateExercisesSkill
        item = _exercise()
        del item["accepted_answers"]
        payload = json.dumps({"exercises": [item]})
        llm = make_llm([payload])

        skill = GenerateExercisesSkill()
        out = skill.run(
            make_input(
                level="a1", topic="Dative case", language="german",
                exercise_type="fill_in_the_blank", exercise_count=1,
            ),
            llm,
        )

        assert out.success is True
        assert out.metadata["exercises"][0]["accepted_answers"] == []

    def test_missing_key_fails_after_retries_exhausted(self):
        from skills.generate_exercises.skill import GenerateExercisesSkill
        bad = json.dumps({"exercises": [{"prompt": "x", "type": "fill_in_the_blank"}]})  # missing correct_answer/error_tag
        llm = make_llm([bad, bad, bad])

        skill = GenerateExercisesSkill()
        out = skill.run(
            make_input(
                level="a1", topic="Dative case", language="german",
                exercise_type="fill_in_the_blank",
            ),
            llm,
        )

        assert out.success is False
        assert out.metadata["exercises"] == []

    def test_unknown_exercise_type_fails_without_llm_call(self):
        """exercise_type is validated against the language's exercise-types map
        before any LLM call — a caller bug (typo'd type) must fail fast, not
        burn a retry loop on an unwinnable prompt."""
        from skills.generate_exercises.skill import GenerateExercisesSkill
        llm = make_llm([])

        skill = GenerateExercisesSkill()
        out = skill.run(
            make_input(
                level="a1", topic="Dative case", language="german",
                exercise_type="not_a_real_type",
            ),
            llm,
        )

        assert out.success is False
        assert out.metadata["exercises"] == []
        llm.complete.assert_not_called()


# ---------------------------------------------------------------------------
# GradeExercisesSkill
# ---------------------------------------------------------------------------

def _item(**overrides) -> dict:
    base = {
        "index": 0,
        "prompt": "Ich fahre ___ meinem Freund. (with)",
        "correct_answer": "mit",
        "error_tag": "noun_declension",
        "topic": "Dative case",
        "user_answer": "bei",
        "already_known_wrong": True,
    }
    base.update(overrides)
    return base


class TestGradeExercisesSkill:

    def test_empty_items_short_circuits_without_llm_call(self):
        from skills.grade_exercises.skill import GradeExercisesSkill
        llm = make_llm([])

        skill = GradeExercisesSkill()
        out = skill.run(make_input(level="a1", items=[], language="german"), llm)

        assert out.success is True
        assert out.metadata["results"] == []
        llm.complete.assert_not_called()

    def test_grades_mixed_batch(self):
        from skills.grade_exercises.skill import GradeExercisesSkill
        items = [
            _item(index=0, already_known_wrong=True),
            _item(index=1, already_known_wrong=False, user_answer="Heute lerne ich Deutsch."),
        ]
        payload = json.dumps({"results": [
            {"index": 0, "correct": False, "feedback": "'bei' takes dative but doesn't mean 'with' here; use 'mit'."},
            {"index": 1, "correct": True, "feedback": ""},
        ]})
        llm = make_llm([payload])

        skill = GradeExercisesSkill()
        out = skill.run(make_input(level="a1", items=items, language="german"), llm)

        assert out.success is True
        results = {r["index"]: r for r in out.metadata["results"]}
        assert results[0]["correct"] is False
        assert results[0]["feedback"]
        assert results[1]["correct"] is True
        assert results[1]["feedback"] == ""

    def test_already_known_wrong_forced_false_even_if_model_disagrees(self):
        """already_known_wrong items were already scored by Python string
        comparison — the model must not be trusted to overturn that verdict."""
        from skills.grade_exercises.skill import GradeExercisesSkill
        items = [_item(index=0, already_known_wrong=True)]
        payload = json.dumps({"results": [
            {"index": 0, "correct": True, "feedback": "actually this is fine"},
        ]})
        llm = make_llm([payload])

        skill = GradeExercisesSkill()
        out = skill.run(make_input(level="a1", items=items, language="german"), llm)

        assert out.success is True
        assert out.metadata["results"][0]["correct"] is False

    def test_feedback_preserved_when_correct(self):
        """Feedback on a correct=true item is kept, not blanked — used for
        non-penalizing notes like flagging a typo that didn't affect the
        grammar rule being tested."""
        from skills.grade_exercises.skill import GradeExercisesSkill
        items = [_item(index=0, already_known_wrong=False)]
        payload = json.dumps({"results": [
            {"index": 0, "correct": True, "feedback": "Note: 'Gester' should be 'Gestern'."},
        ]})
        llm = make_llm([payload])

        skill = GradeExercisesSkill()
        out = skill.run(make_input(level="a1", items=items, language="german"), llm)

        assert out.success is True
        assert out.metadata["results"][0]["correct"] is True
        assert out.metadata["results"][0]["feedback"] == "Note: 'Gester' should be 'Gestern'."

    def test_feedback_optional_when_correct(self):
        from skills.grade_exercises.skill import GradeExercisesSkill
        items = [_item(index=0, already_known_wrong=False)]
        payload = json.dumps({"results": [
            {"index": 0, "correct": True, "feedback": ""},
        ]})
        llm = make_llm([payload])

        skill = GradeExercisesSkill()
        out = skill.run(make_input(level="a1", items=items, language="german"), llm)

        assert out.success is True
        assert out.metadata["results"][0]["feedback"] == ""

    def test_missing_feedback_for_incorrect_item_triggers_retry(self):
        from skills.grade_exercises.skill import GradeExercisesSkill
        items = [_item(index=0, already_known_wrong=False)]
        bad = json.dumps({"results": [{"index": 0, "correct": False, "feedback": ""}]})
        good = json.dumps({"results": [{"index": 0, "correct": False, "feedback": "explanation"}]})
        llm = make_llm([bad, good])

        skill = GradeExercisesSkill()
        out = skill.run(make_input(level="a1", items=items, language="german"), llm)

        assert out.success is True
        assert out.metadata["results"][0]["feedback"] == "explanation"
        assert llm.complete.call_count == 2

    def test_count_mismatch_triggers_retry(self):
        from skills.grade_exercises.skill import GradeExercisesSkill
        items = [_item(index=0), _item(index=1, already_known_wrong=False)]
        too_few = json.dumps({"results": [{"index": 0, "correct": False, "feedback": "x"}]})
        full = json.dumps({"results": [
            {"index": 0, "correct": False, "feedback": "x"},
            {"index": 1, "correct": True, "feedback": ""},
        ]})
        llm = make_llm([too_few, full])

        skill = GradeExercisesSkill()
        out = skill.run(make_input(level="a1", items=items, language="german"), llm)

        assert out.success is True
        assert len(out.metadata["results"]) == 2
        assert llm.complete.call_count == 2

    def test_unknown_index_triggers_retry(self):
        from skills.grade_exercises.skill import GradeExercisesSkill
        items = [_item(index=0)]
        bad = json.dumps({"results": [{"index": 7, "correct": False, "feedback": "x"}]})
        good = json.dumps({"results": [{"index": 0, "correct": False, "feedback": "x"}]})
        llm = make_llm([bad, good])

        skill = GradeExercisesSkill()
        out = skill.run(make_input(level="a1", items=items, language="german"), llm)

        assert out.success is True
        assert out.metadata["results"][0]["index"] == 0
        assert llm.complete.call_count == 2

    def test_duplicate_index_triggers_retry(self):
        from skills.grade_exercises.skill import GradeExercisesSkill
        items = [_item(index=0), _item(index=1, already_known_wrong=False)]
        bad = json.dumps({"results": [
            {"index": 0, "correct": False, "feedback": "x"},
            {"index": 0, "correct": False, "feedback": "x"},
        ]})
        good = json.dumps({"results": [
            {"index": 0, "correct": False, "feedback": "x"},
            {"index": 1, "correct": True, "feedback": ""},
        ]})
        llm = make_llm([bad, good])

        skill = GradeExercisesSkill()
        out = skill.run(make_input(level="a1", items=items, language="german"), llm)

        assert out.success is True
        assert llm.complete.call_count == 2

    def test_missing_key_fails_after_retries_exhausted(self):
        from skills.grade_exercises.skill import GradeExercisesSkill
        items = [_item(index=0)]
        bad = json.dumps({"results": [{"index": 0}]})  # missing 'correct'
        llm = make_llm([bad, bad, bad])

        skill = GradeExercisesSkill()
        out = skill.run(make_input(level="a1", items=items, language="german"), llm)

        assert out.success is False
        assert out.metadata["results"] == []
        assert "error" in out.metadata
        assert "error" in out.metadata
