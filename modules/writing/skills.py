from skills.detect_mistakes.skill import DetectMistakesSkill
from skills.btw_handler.skill import BtwHandlerSkill

def get_writing_skills() -> dict:
    """Returns the instantiated skills required by the writing module."""
    return {
        "detect_mistakes": DetectMistakesSkill(),
        "btw_handler": BtwHandlerSkill(),
    }
