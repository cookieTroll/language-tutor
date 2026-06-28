from skills.detect_mistakes.skill import DetectMistakesSkill
from skills.classify_mistakes.skill import ClassifyMistakesSkill
from skills.explain_mistakes.skill import ExplainMistakesSkill
from skills.write_correction.skill import WriteCorrectionSkill
from skills.estimate_text_level.skill import EstimateTextLevelSkill
from skills.summarise_session.writing.skill import SummariseWritingSessionSkill
from skills.btw_handler.skill import BtwHandlerSkill


def get_writing_skills() -> dict:
    """Returns the instantiated skills required by the writing module."""
    return {
        "detect_mistakes":           DetectMistakesSkill(),
        "classify_mistakes":         ClassifyMistakesSkill(),
        "explain_mistakes":          ExplainMistakesSkill(),
        "write_correction":          WriteCorrectionSkill(),
        "estimate_text_level":       EstimateTextLevelSkill(),
        "summarise_writing_session": SummariseWritingSessionSkill(),
        "btw_handler":               BtwHandlerSkill(),
    }
