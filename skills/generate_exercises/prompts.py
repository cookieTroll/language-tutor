GENERIC_SCOPE_FALLBACK = (
    "If the topic name above contains a qualifier clause (specific verbs, "
    "\"regular\" vs \"irregular\", a named subset, etc.), treat that clause as "
    "a hard scope boundary — every exercise must stay within it."
)

GENERATE_EXERCISES_PROMPT = """\
Generate {exercise_count} {language} grammar exercises on:
"{topic}"

Level: {level}

{scope_block}

Allowed exercise types — choose 2-3 types that best fit the topic and level,
and GROUP them into batches: put every exercise of one type consecutively in
the output array (e.g. 4-5 fill_in_the_blank items in a row) before moving to
the next type, rather than interleaving different types one at a time. This
lets the student work through one exercise style at a time instead of
switching format every line.
Types marked (exact) have one unambiguous correct answer; types marked (llm)
allow multiple valid phrasings, so just supply one reference correct_answer
and don't worry about exact wording:
{exercise_types}

Allowed error_tag values (use EXACTLY one of these strings for each exercise):
{taxonomy}

For each exercise, provide:
- prompt: the exercise text exactly as shown to the student
- type: one of the exercise type names listed above
- correct_answer: the reference correct answer
- accepted_answers: (optional) list of other acceptable phrasings — exact-match types only, [] otherwise
- error_tag: the single best matching tag from the taxonomy above
- distractor_hint: the common wrong-answer pattern this exercise targets

Every exercise must be genuinely about "{topic}" — do not reuse or adapt any
example from these instructions, they are format illustrations only.

Return JSON only. No markdown.
{{
  "exercises": [
    {{
      "prompt": "<exercise text testing {topic}, in {language}>",
      "type": "<one of the exercise type names above>",
      "correct_answer": "<the reference correct answer>",
      "accepted_answers": [],
      "error_tag": "<a valid taxonomy tag>",
      "distractor_hint": "<the common wrong-answer pattern this targets>"
    }}
  ]
}}"""
