"""Layer 2c — Level & Progress: level-up decision.

Deliberately not an LLM skill: whether to suggest a level-up is a deterministic
threshold crossing on ModuleMastery.mastery_ratio (grammar: topics_mastered /
topics_total at the current level, reusing GRAMMAR_MASTERY_THRESHOLD), not a
fuzzy judgment call. Kept as a skill file (rather than inline orchestrator
code) so the threshold and next-level lookup are unit-testable in isolation,
and to match the layout of every other skill in the tree.

The caller (orchestrator) is responsible for confirming with the user before
writing the suggested level via store.write_level(..., source="estimated") —
this skill only ever suggests, never writes.
"""
from skills.protocols import SkillInput, SkillOutput
from llm.base import BaseLLM

LEVEL_ORDER = ["a1", "a2", "b1", "b2", "c1", "c2"]
LEVEL_UP_THRESHOLD = 1.0  # all curated grammar topics for the current level mastered


class CefrEstimatorSkill:
    name = "cefr_estimator"
    description = (
        "Utility: decides whether a user's grammar mastery at their current CEFR "
        "level crosses the level-up threshold, and if so, what the next level is."
    )
    skill_type = "utility"

    def run(self, input: SkillInput, llm: BaseLLM) -> SkillOutput:
        mastery = input.parameters["mastery"]  # orchestrator.mastery.ModuleMastery (grammar)
        current_level = input.level.lower()

        should_level_up = mastery.topics_total > 0 and mastery.mastery_ratio >= LEVEL_UP_THRESHOLD
        next_level = None
        if should_level_up and current_level in LEVEL_ORDER:
            idx = LEVEL_ORDER.index(current_level)
            if idx + 1 < len(LEVEL_ORDER):
                next_level = LEVEL_ORDER[idx + 1]
            else:
                should_level_up = False  # already at C2 — nothing higher to suggest

        return SkillOutput(
            skill_name=self.name,
            success=True,
            metadata={"should_level_up": should_level_up, "next_level": next_level},
        )
