from skills.cefr_estimator.skill import CefrEstimatorSkill
from skills.protocols import SkillInput
from orchestrator.mastery import ModuleMastery


def _run(level: str, mastery: ModuleMastery):
    return CefrEstimatorSkill().run(
        SkillInput(user_id="user1", level=level, parameters={"mastery": mastery}),
        llm=None,
    )


def test_suggests_level_up_when_all_topics_mastered():
    mastery = ModuleMastery(module="grammar", topics_total=2, topics_mastered=2, mastery_ratio=1.0)
    out = _run("a1", mastery)
    assert out.metadata["should_level_up"] is True
    assert out.metadata["next_level"] == "a2"


def test_no_suggestion_when_below_threshold():
    mastery = ModuleMastery(module="grammar", topics_total=2, topics_mastered=1, mastery_ratio=0.5)
    out = _run("a1", mastery)
    assert out.metadata["should_level_up"] is False
    assert out.metadata["next_level"] is None


def test_no_suggestion_when_no_topics_configured():
    """topics_total=0 (e.g. language has no grammar_topics map) must not look like
    a vacuously-mastered 0/0 level-up."""
    mastery = ModuleMastery(module="grammar", topics_total=0, topics_mastered=0, mastery_ratio=0.0)
    out = _run("a1", mastery)
    assert out.metadata["should_level_up"] is False


def test_no_suggestion_past_c2():
    mastery = ModuleMastery(module="grammar", topics_total=2, topics_mastered=2, mastery_ratio=1.0)
    out = _run("c2", mastery)
    assert out.metadata["should_level_up"] is False
    assert out.metadata["next_level"] is None
