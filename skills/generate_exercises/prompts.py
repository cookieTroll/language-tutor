GENERATE_EXERCISES_PROMPT = """\
Generate {exercise_count} {language} grammar exercises on:
"{topic}"

Level: {level}

Allowed exercise types — choose whichever mix best fits the topic and level.
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

Return JSON only. No markdown.
{{
  "exercises": [
    {{
      "prompt": "Ich fahre ___ meinem Freund. (with)",
      "type": "fill_in_the_blank",
      "correct_answer": "mit",
      "accepted_answers": [],
      "error_tag": "<a valid taxonomy tag>",
      "distractor_hint": "Students often confuse 'mit' + accusative"
    }}
  ]
}}"""
