from skills.select_grammar.skill import SelectGrammarSkill
from skills.dump_grammar.skill import DumpGrammarSkill
from skills.generate_exercises.skill import GenerateExercisesSkill
from skills.grade_exercises.skill import GradeExercisesSkill
from skills.btw_handler.skill import BtwHandlerSkill


def get_grammar_skills() -> dict:
    """Returns the instantiated skills required by the grammar module."""
    return {
        "select_grammar":     SelectGrammarSkill(),
        "dump_grammar":       DumpGrammarSkill(),
        "generate_exercises": GenerateExercisesSkill(),
        "grade_exercises":    GradeExercisesSkill(),
        "btw_handler":        BtwHandlerSkill(),
    }
