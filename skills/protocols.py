from typing import Protocol, Literal
from pydantic import BaseModel, field_validator
from llm.base import BaseLLM

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
