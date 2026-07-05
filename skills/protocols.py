from typing import Protocol, Literal, Callable, TypeVar
from pydantic import BaseModel, field_validator
from llm.base import BaseLLM, LLMMessage

T = TypeVar("T")

class SelfCorrectionError(Exception):
    def __init__(self, message: str, raw_response: str | None = None):
        super().__init__(message)
        self.raw_response = raw_response

def call_with_self_correction(
    llm: BaseLLM,
    messages: list[LLMMessage],
    parse_fn: Callable[[str], T],
    temperature: float = 0.1
) -> T:
    current_messages = list(messages)
    max_attempts = getattr(llm.config, "max_skill_retries", 3)
    if not isinstance(max_attempts, int):
        max_attempts = 3
        
    for attempt in range(1, max_attempts + 1):
        try:
            # parse_fn does both JSON parsing and schema/business-rule validation, so
            # a raise here can mean "not valid JSON" or "valid JSON, wrong shape" —
            # either way the model gets the same chance to self-correct below.
            response = llm.complete(current_messages, temperature=temperature)
            text = response.text.strip()
            return parse_fn(text)
        except Exception as e:
            if attempt == max_attempts:
                err_msg = str(e)
                show_tag = getattr(llm.config, "show_cut_by_limit_tag", True)
                if not isinstance(show_tag, bool):
                    show_tag = True
                if 'response' in locals() and response.truncated and show_tag:
                    err_msg += " [TRUNCATED BY LIMIT]"
                raise SelfCorrectionError(err_msg, raw_response=text if 'text' in locals() else None) from e
            
            # Append self-correction feedback messages
            if 'text' in locals():
                current_messages.append(LLMMessage(role="assistant", content=text))
            current_messages.append(LLMMessage(
                role="user",
                content=f"Your previous response failed to parse correctly. Error: {e}. Please output the correct format adhering strictly to the guidelines, and ensure it is fully completed (do not truncate)."
            ))

class SkillInput(BaseModel):
    """Base input for all skills. Each skill defines a typed subclass."""
    user_id: str
    level: str
    parameters: dict                      # skill-specific inputs

    @field_validator("level")
    @classmethod
    def validate_level(cls, v: str) -> str:
        valid_levels = {"a1", "a2", "b1", "b2", "c1", "c2"}
        if v.lower() not in valid_levels:
            raise ValueError(f"Invalid CEFR level: '{v}'. Allowed: {valid_levels}")
        return v.lower()

class SkillOutput(BaseModel):
    """Base output for all skills. Each skill defines a typed subclass."""
    skill_name: str
    success: bool
    metadata: dict                        # skill-specific outputs

class SkillProtocol(Protocol):
    name: str
    description: str
    skill_type: Literal["session", "utility"]
    # session  — full lifecycle, invoked by module, result persisted
    # utility  — invoked inline mid-session (e.g. btw_handler, explain_grammar)
    #            no session file written, returned in ModuleResult.metadata

    def run(self, input: SkillInput, llm: BaseLLM) -> SkillOutput:
        """
        Execute skill. Pure — no storage calls, no provider SDK calls.
        LLM injected, not constructed inside.
        """
        ...
