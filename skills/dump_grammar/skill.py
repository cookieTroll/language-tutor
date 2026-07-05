from llm.base import BaseLLM, LLMMessage
from lang.loader import get_grammar_topics
from skills.protocols import SkillProtocol, SkillInput, SkillOutput
from skills.dump_grammar.prompts import DUMP_GRAMMAR_PROMPT, GENERIC_SCOPE_FALLBACK


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
        explanation_language = (input.parameters.get("explanation_language") or "english").capitalize()

        if not topic:
            return SkillOutput(
                skill_name=self.name,
                success=False,
                metadata={"explanation": "", "error": "No topic provided."},
            )

        # dump_grammar and generate_exercises are independent LLM calls given
        # only the topic string — without an explicit scope boundary, one can
        # explain a narrower slice (e.g. regular verbs) while the other tests a
        # wider one (e.g. all verbs). Curated topics may carry in_scope/out_of_scope;
        # ad hoc/minor topics fall back to a generic "respect the topic's own
        # qualifier clause" instruction.
        topics_map = get_grammar_topics(language)
        matched = topics_map.scope_for(topic) if topics_map else None
        scope_block = (matched.format_scope_for_prompt() if matched else "") or GENERIC_SCOPE_FALLBACK

        prompt = DUMP_GRAMMAR_PROMPT.format(
            language=language,
            explanation_language=explanation_language,
            topic=topic,
            level=input.level.upper(),
            scope_block=scope_block,
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
