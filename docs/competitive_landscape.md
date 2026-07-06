# Competitive Landscape — Auto-Graded Writing

Summary of how the writing module's auto-grading pipeline (`docs/writing.md`) compares to
existing tools that give learners automated feedback on free-text writing. Written 2026-07-05
for reference by other agents/collaborators working on this feature; re-verify claims before
relying on them for anything time-sensitive (competitor products change).

## Our pipeline, in one line

Free-text submission → parallel CEFR level estimate + mistake detection → context-based
false-positive verification → per-language taxonomy classification → level-calibrated
explanation → corrected rewrite + severity-tagged summary, with an inline `/btw` Q&A loop
mid-session. See `modules/writing/pipeline.py`.

## Closest comparators

| Tool | Mechanism | Overlap | Gap vs. ours |
|---|---|---|---|
| **Cambridge Write & Improve** | Supervised ML classifier trained on 30M-word error-annotated corpus | Free-text submission, CEFR-aligned feedback, revision loop — nearest existing analog | English-only; no false-positive verification step, no error taxonomy, no severity tiers, no level-calibrated explanation depth |
| **Duolingo Max** | GPT-4 "Explain My Answer" / roleplay | LLM-based feedback | Scoped to short in-lesson answers, not free-essay grading with structured error output |
| **Busuu** | Human peer correction (native speakers) | Corrective feedback on learner writing | Not automated; quality/turnaround depends on volunteer availability (minutes to days) |
| **Grammarly** | General-purpose grammar/style correction | Error detection + correction | No CEFR calibration, no L2 pedagogy, not multilingual for language-learning use |
| Academic prototypes (CWLA/CEFR-J scoring, FeedbackWriter, GPT-4 L2 analytic assessment studies) | LLM/ML CEFR scoring | Validates the "LLM as writing-feedback engine" approach | Research prototypes, not shipped multilingual products |

Informal baseline: many learners just paste text into ChatGPT and ask for corrections. Our
pipeline's edge over that is structural — verification, taxonomy, severity — not just "LLM
graded my writing."

## Differentiation

No comparator bundles all of:
1. **Multi-language taxonomy** (`lang/maps/taxonomy/`) rather than English-only.
2. **False-positive verification** — re-checks each candidate error against sentence context
   before it reaches the learner (`skills/verify_mistakes/`).
3. **Severity tagging** (critical/expected/minor) alongside CEFR-calibrated explanation depth.
4. **Inline `/btw` Q&A** during composition, not just post-hoc feedback.

Write & Improve is the strongest existing match in spirit but is English-only and lacks (2)-(4).

## Open question for positioning

Since the strongest analog is free and English-only, the biggest differentiation value is
likely in **non-English target languages with this level of structured pedagogy** — that gap
isn't filled by any product found in this pass.
