import time
from dataclasses import dataclass, field
from llm.base import BaseLLM
from modules.protocols import ModuleContext
from skills.protocols import SkillInput


@dataclass
class StepTiming:
    step: int
    skill: str
    duration_s: float


@dataclass
class PipelineResult:
    detector_success: bool
    detector_error: str
    explained_mistakes: list[dict]
    corrected_text: str
    tips: list[str]
    session_summary: str
    text_level_estimate: str | None = None
    comparison_note: str | None = None
    step_timings: list[StepTiming] = field(default_factory=list)


class WritingPipeline:
    """
    Sequences the 6-skill evaluator pipeline for a writing session.

    Execution order (note: Step 5 runs before Step 1 — it is independent):

        Step 5  estimate_text_level   — CEFR estimate of the submitted text; runs
                                        unconditionally and is carried through even
                                        if the error pipeline short-circuits.

        Step 1  detect_mistakes       — raw mistake detection on the user text;
                                        GATE: if this fails (bad JSON / LLM error)
                                        the pipeline returns early with
                                        detector_success=False and no further LLM
                                        calls are made.

        Step 2  classify_mistakes     — maps raw fragments to taxonomy error_tags
                                        (e.g. verb_conjugation, article_gender).

        Step 3  explain_mistakes      — adds a learner-facing pedagogical explanation
                                        to each classified mistake.

        Step 4  write_correction      — rewrites the full user text with all mistakes
                                        corrected; preserves voice and register.

        Step 6  summarise_writing_session — enriches mistakes with severity labels
                                        (critical / expected / minor), generates
                                        session_summary and tips[], and populates
                                        comparison_note if prior session data is
                                        available.

    Data flow: each step receives only the output it needs from previous steps —
    raw_mistakes → classified_mistakes → explained_mistakes flows linearly.
    Steps 5 and 6 both receive user_text and writing_prompt directly.
    """

    def __init__(self, skills: dict):
        self.skills = skills

    def run(
        self,
        ctx: ModuleContext,
        user_text: str,
        writing_prompt: str,
        min_words: int,
        llm: BaseLLM,
        io=None,
        enable_timing: bool = True,
    ) -> PipelineResult:
        def _progress(msg: str) -> None:
            if io:
                io.output(msg)

        timings: list[StepTiming] = []

        def _timed(step: int, skill_name: str, skill_input: SkillInput):
            if not enable_timing:
                return self.skills[skill_name].run(skill_input, llm)
            t0 = time.perf_counter()
            result = self.skills[skill_name].run(skill_input, llm)
            timings.append(StepTiming(step=step, skill=skill_name, duration_s=round(time.perf_counter() - t0, 3)))
            return result

        # Step 5: estimate text CEFR level — independent of error pipeline, run first
        _progress("[1/6] Estimating text level…")
        level_output = _timed(1, "estimate_text_level", SkillInput(
            user_id=ctx.user_id, level=ctx.level,
            parameters={"user_text": user_text, "writing_prompt": writing_prompt, "language": ctx.language},
        ))
        text_level_estimate = level_output.metadata.get("text_level_estimate")

        # Step 1: detect raw mistakes
        _progress("[2/6] Detecting mistakes…")
        detector_output = _timed(2, "detect_mistakes", SkillInput(
            user_id=ctx.user_id, level=ctx.level,
            parameters={
                "user_text": user_text, "writing_prompt": writing_prompt,
                "recurring_errors": list(ctx.error_frequency.keys()), "language": ctx.language,
            },
        ))
        if not detector_output.success:
            return PipelineResult(
                detector_success=False,
                detector_error=detector_output.metadata.get("error", "Unknown error"),
                explained_mistakes=[],
                corrected_text=user_text,
                tips=[],
                session_summary="",
                text_level_estimate=text_level_estimate,
                step_timings=timings,
            )
        raw_mistakes = detector_output.metadata.get("raw_mistakes", [])

        # Step 2: classify against taxonomy
        _progress("[3/6] Classifying mistakes…")
        classify_output = _timed(3, "classify_mistakes", SkillInput(
            user_id=ctx.user_id, level=ctx.level,
            parameters={"raw_mistakes": raw_mistakes, "language": ctx.language},
        ))
        classified_mistakes = classify_output.metadata.get("classified_mistakes", [])

        # Step 3: add pedagogical explanations
        _progress("[4/6] Adding explanations…")
        explain_output = _timed(4, "explain_mistakes", SkillInput(
            user_id=ctx.user_id, level=ctx.level,
            parameters={"classified_mistakes": classified_mistakes, "language": ctx.language},
        ))
        explained_mistakes = explain_output.metadata.get("explained_mistakes", [])

        # Step 4: write corrected text
        _progress("[5/6] Writing corrected version…")
        correction_output = _timed(5, "write_correction", SkillInput(
            user_id=ctx.user_id, level=ctx.level,
            parameters={"user_text": user_text, "explained_mistakes": explained_mistakes, "language": ctx.language},
        ))
        corrected_text = correction_output.metadata.get("corrected_text", user_text)

        # Step 6: enrich mistakes with severity, generate summary and tips
        _progress("[6/6] Generating summary and tips…")
        summary_output = _timed(6, "summarise_writing_session", SkillInput(
            user_id=ctx.user_id,
            level=ctx.level,
            parameters={
                "user_text": user_text,
                "explained_mistakes": explained_mistakes,
                "text_level_estimate": text_level_estimate,
                "writing_prompt": writing_prompt,
                "min_words": min_words,
                "language": ctx.language,
            },
        ))
        return PipelineResult(
            detector_success=True,
            detector_error="",
            explained_mistakes=summary_output.metadata.get("mistakes", explained_mistakes),
            corrected_text=corrected_text,
            tips=summary_output.metadata.get("tips", []),
            session_summary=summary_output.metadata.get("session_summary", ""),
            text_level_estimate=text_level_estimate,
            comparison_note=summary_output.metadata.get("comparison_note"),
            step_timings=timings,
        )
