import re
from skills.protocols import SkillProtocol, SkillInput, SkillOutput
from llm.base import BaseLLM, LLMMessage
from skills.btw_handler.prompts import BTW_PROMPT, BTW_WORD_EXTRACTION_PROMPT


def _format_evaluation_context(session_context: dict) -> str:
    """Formats post-evaluation pipeline fields (mistakes/correction/tips/summary)
    for injection into BTW_PROMPT, so "why is this wrong?" follow-up questions are
    grounded in the actual evaluation already shown to the user — not re-derived
    from scratch. Empty string (and the prompt's {evaluation_context} line stays
    blank) when called before evaluation has happened, e.g. mid-writing /btw."""
    mistakes = session_context.get("explained_mistakes")
    if not mistakes:
        return ""

    lines = "\n".join(
        f"  - '{m.get('fragment', '')}' → '{m.get('correction', '')}' "
        f"({m.get('error_tag', '')}): {m.get('explanation', '')}"
        for m in mistakes
    )
    parts = [f"- Mistakes found in the student's submission:\n{lines}"]

    if session_context.get("corrected_text"):
        parts.append(f"- Corrected text: {session_context['corrected_text']}")
    if session_context.get("session_summary"):
        parts.append(f"- Session summary: {session_context['session_summary']}")
    if session_context.get("tips"):
        parts.append(f"- Tips given: {'; '.join(session_context['tips'])}")

    return "\n".join(parts)


class BtwHandlerSkill(SkillProtocol):
    name = "btw_handler"
    description = "Utility: Answers quick, mid-session side questions from the user and extracts vocabulary flags."
    skill_type = "utility"

    def _regex_extract(self, question: str) -> str | None:
        # Match words in quotes
        match = re.search(r'["\'`„“]([^"\'`„“]+)["\'`„“]', question)
        if match:
            return match.group(1).strip().lower()
        
        # Match common English/German phrasing patterns
        patterns = [
            r'(?i)what does\s+([A-Za-zÄäÖöÜüß\-]+)\s+mean',
            r'(?i)meaning of\s+([A-Za-zÄäÖöÜüß\-]+)',
            r'(?i)how do (?:i|we)\s+say\s+([A-Za-zÄäÖöÜüß\-]+)',
            r'(?i)what is\s+([A-Za-zÄäÖöÜüß\-]+)',
            r'(?i)was bedeutet\s+([A-Za-zÄäÖöÜüß\-]+)'
        ]
        for pat in patterns:
            match = re.search(pat, question)
            if match:
                return match.group(1).strip().lower()
        return None

    def run(self, input: SkillInput, llm: BaseLLM) -> SkillOutput:
        question = input.parameters.get("question", "")
        session_context = input.parameters.get("session_context", {})
        
        if not question.strip():
            return SkillOutput(
                skill_name=self.name,
                success=False,
                metadata={"answer": "You didn't ask a question.", "flagged_word": None}
            )

        # 1. Generate the answer
        prompt = BTW_PROMPT.format(
            module=session_context.get("module", "unknown"),
            topic=session_context.get("topic", "unknown"),
            user_text_so_far=session_context.get("user_text_so_far", ""),
            level=input.level,
            language=session_context.get("language", "German").capitalize(),
            evaluation_context=_format_evaluation_context(session_context),
            question=question
        )
        
        lang_cap = session_context.get("language", "German").capitalize()
        messages = [
            LLMMessage(
                role="system",
                content=(
                    f"You are a helpful, brief {lang_cap} tutor. "
                    "You explain grammar and vocabulary concepts to students. "
                    f"Always write your explanations in English, using {lang_cap} only for translations, vocabulary words, and examples. "
                    f"CRITICAL: Never invent or hallucinate words in {lang_cap}. If you do not know the exact translation or grammar rule, state that you do not know."
                )
            ),
            LLMMessage(role="user", content=prompt)
        ]
        
        try:
            response = llm.complete(messages, temperature=0.2)
            answer = response.text.strip()
            show_tag = getattr(llm.config, "show_cut_by_limit_tag", True)
            if not isinstance(show_tag, bool):
                show_tag = True
            if response.truncated and show_tag:
                answer += "\n[TRUNCATED BY LIMIT]"
        except Exception as e:
            err_msg = f"Error answering question: {e}"
            show_tag = getattr(llm.config, "show_cut_by_limit_tag", True)
            if not isinstance(show_tag, bool):
                show_tag = True
            if 'response' in locals() and response.truncated and show_tag:
                err_msg += " [TRUNCATED BY LIMIT]"
                
            metadata = {"answer": err_msg, "flagged_word": None}
            show_inc = getattr(llm.config, "show_incomplete_responses", False)
            if not isinstance(show_inc, bool):
                show_inc = False
            if 'answer' in locals() and show_inc:
                metadata["raw_response"] = answer
                
            return SkillOutput(
                skill_name=self.name,
                success=False,
                metadata=metadata
            )

        # 2. Extract flagged word
        flagged_word = self._regex_extract(question)
        
        if not flagged_word:
            # Fall back to LLM-based extraction
            extraction_prompt = BTW_WORD_EXTRACTION_PROMPT.format(
                question=question,
                language=session_context.get("language", "German").capitalize()
            )
            extract_messages = [
                LLMMessage(role="system", content="You are a linguistic extraction utility."),
                LLMMessage(role="user", content=extraction_prompt)
            ]
            try:
                extract_response = llm.complete(extract_messages, temperature=0.0)
                extracted = extract_response.text.strip().lower()
                # Clean any punctuation
                extracted = re.sub(r'[.\'"`„“]', '', extracted).strip()
                if extracted and extracted != "none":
                    flagged_word = extracted
            except Exception:
                # Silently ignore extraction failures for robustness
                flagged_word = None

        return SkillOutput(
            skill_name=self.name,
            success=True,
            metadata={"answer": answer, "flagged_word": flagged_word}
        )
