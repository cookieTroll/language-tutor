import re
from skills.protocols import SkillProtocol, SkillInput, SkillOutput
from llm.base import BaseLLM, LLMMessage
from skills.btw_handler.prompts import BTW_PROMPT, BTW_WORD_EXTRACTION_PROMPT

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
            question=question
        )
        
        messages = [
            LLMMessage(role="system", content="You are a helpful, brief German tutor assistant."),
            LLMMessage(role="user", content=prompt)
        ]
        
        try:
            response = llm.complete(messages, temperature=0.2)
            answer = response.text.strip()
            if response.truncated and llm.config.show_cut_by_limit_tag:
                answer += "\n[TRUNCATED BY LIMIT]"
        except Exception as e:
            err_msg = f"Error answering question: {e}"
            if 'response' in locals() and response.truncated and llm.config.show_cut_by_limit_tag:
                err_msg += " [TRUNCATED BY LIMIT]"
                
            metadata = {"answer": err_msg, "flagged_word": None}
            if 'answer' in locals() and llm.config.show_incomplete_responses:
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
            extraction_prompt = BTW_WORD_EXTRACTION_PROMPT.format(question=question)
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
