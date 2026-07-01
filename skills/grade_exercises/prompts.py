GRADE_EXERCISES_PROMPT = """\
Grade these {level} {language} grammar exercises on "{topic}". Some answers are
already known to be wrong (marked already_known_wrong: true) — for those, just
explain why the reference answer is correct and theirs isn't, don't re-judge
correctness. For the rest, the reference correct_answer is ONE example of a
valid answer, not the only acceptable one — an answer using different content
or vocabulary is still correct as long as it applies the target grammar rule
correctly. Judge each answer against the grammar rule being tested, not
against how closely it matches the reference text. Only mark an answer wrong
if it violates the grammar rule itself (wrong case, wrong tense, wrong word
order, etc.), not because it says something different from the example.

{items_json}

MANDATORY: process every single item in the list above, including
already_known_wrong ones — do not skip any item. Every item you mark
correct=false MUST have a non-empty feedback string explaining the mistake;
never leave feedback blank for an incorrect item, even if the explanation is
short.

Return JSON only. No markdown.
{{
  "results": [
    {{"index": <int>, "correct": <true|false>, "feedback": "<1-3 sentences, direct; REQUIRED and non-empty whenever correct is false>"}}
  ]
}}"""
