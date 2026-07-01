from llm.base import BaseLLM, LLMMessage
from skills.protocols import SkillProtocol, SkillInput, SkillOutput
from skills.dump_grammar.prompts import DUMP_GRAMMAR_PROMPT


class DumpGrammarSkill(SkillProtocol):
    name = "dump_grammar"
    description = (
        "Produces a comprehensive, textbook-style explanation of a grammar topic "
        "(rules, tables, examples, common mistakes) to display before exercises."
    )
    skill_type = "session"

    def run(self, input: SkillInput, llm: BaseLLM) -> SkillOutput:
        topic = input.parameters.get("topic", "").strip()
        language = input.parameters.get("language", "German").capitalize()

        if not topic:
            return SkillOutput(
                skill_name=self.name,
                success=False,
                metadata={"explanation": "", "error": "No topic provided."},
            )

        prompt = DUMP_GRAMMAR_PROMPT.format(
            language=language,
            topic=topic,
            level=input.level.upper(),
        )
        messages = [LLMMessage(role="user", content=prompt)]

        try:
            response = llm.complete(messages, temperature=0.3)
        except Exception as e:
            return SkillOutput(
                skill_name=self.name,
                success=False,
                metadata={"explanation": "", "error": str(e)},
            )

        explanation = response.text.strip()
        show_tag = getattr(llm.config, "show_cut_by_limit_tag", True)
        if not isinstance(show_tag, bool):
            show_tag = True
        if response.truncated and show_tag:
            explanation += "\n\n[TRUNCATED BY LIMIT]"

        if not explanation:
            return SkillOutput(
                skill_name=self.name,
                success=False,
                metadata={"explanation": "", "error": "Empty explanation returned."},
            )

        return SkillOutput(skill_name=self.name, success=True, metadata={"explanation": explanation})
