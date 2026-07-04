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

Use EXACTLY this exercise type for every exercise below — do not use any other
type and do not vary the type across exercises. The student works through one
exercise style per round, and can ask for another round afterward if they want
to practice a different angle on the same topic:
{exercise_type_line}

Allowed error_tag values (use EXACTLY one of these strings for each exercise):
{taxonomy}

For each exercise, provide:
- prompt: the exercise text exactly as shown to the student
- type: must be exactly "{exercise_type}"
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
      "type": "{exercise_type}",
      "correct_answer": "<the reference correct answer>",
      "accepted_answers": [],
      "error_tag": "<a valid taxonomy tag>",
      "distractor_hint": "<the common wrong-answer pattern this targets>"
    }}
  ]
}}"""
