import json
import re

from llm.base import BaseLLM, LLMMessage
from skills.protocols import SkillProtocol, SkillInput, SkillOutput, call_with_self_correction, SelfCorrectionError
from skills.verify_mistakes.prompts import VERIFY_MISTAKES_PROMPT


class VerifyMistakesSkill(SkillProtocol):
    name = "verify_mistakes"
    description = (
        "Step 1.5: Re-checks each detect_mistakes candidate against its original "
        "sentence context and drops false positives before classification — "
        "detect_mistakes judges the whole text in one pass and can misjudge a "
        "fragment (e.g. correct verb-second inversion) in isolation."
    )
    skill_type = "session"

    def run(self, input: SkillInput, llm: BaseLLM) -> SkillOutput:
        raw_mistakes = input.parameters.get("raw_mistakes", [])
        user_text = input.parameters.get("user_text", "")
        language = input.parameters.get("language", "German").capitalize()

        if not raw_mistakes:
            return SkillOutput(skill_name=self.name, success=True, metadata={"verified_mistakes": []})

        prompt = VERIFY_MISTAKES_PROMPT.format(
            language=language,
            user_text=user_text,
            raw_mistakes=json.dumps(raw_mistakes, ensure_ascii=False, indent=2),
        )
        messages = [
            LLMMessage(
                role="system",
                content=(
                    f"You are a precise, skeptical {language} language teacher "
                    "proofreading a candidate error list against its source text."
                ),
            ),
            LLMMessage(role="user", content=prompt),
        ]

        def parse(text: str) -> list[dict]:
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\n?", "", text)
                text = re.sub(r"\n?```$", "", text)
                text = text.strip()
            data = json.loads(text)
            verified = data.get("verified", [])

            keep_by_fragment: dict[str, bool] = {}
            for item in verified:
                if not isinstance(item, dict) or "fragment" not in item:
                    raise ValueError(f"Malformed verified item: {item!r}")
                keep_by_fragment[str(item["fragment"])] = bool(item.get("keep", False))

            # Fail closed on a structural mismatch (a candidate the model never
            # addressed) rather than silently keeping or silently dropping it.
            missing = [m["fragment"] for m in raw_mistakes if m["fragment"] not in keep_by_fragment]
            if missing:
                raise ValueError(f"No verdict returned for fragment(s): {missing!r}")

            return [m for m in raw_mistakes if keep_by_fragment[m["fragment"]]]

        try:
            kept = call_with_self_correction(llm, messages, parse, temperature=0.1)
            return SkillOutput(skill_name=self.name, success=True, metadata={"verified_mistakes": kept})
        except SelfCorrectionError as exc:
            # Fail open: if verification itself breaks, don't silently wipe out every
            # detect_mistakes candidate — trust the original list rather than losing
            # real errors to a broken filtering step.
            return SkillOutput(
                skill_name=self.name,
                success=False,
                metadata={"verified_mistakes": raw_mistakes, "error": str(exc)},
            )
