SELECT_GRAMMAR_PROMPT = """\
You are selecting a {language} grammar topic for a {level} learner.

Curated major topics for this language/level (YAML — the syllabus backbone):
{grammar_topics_yaml}

Recurring errors (error_tag → count):
{error_frequency_json}

Recently covered topics (avoid):
{recent_topics}

Prioritise a major topic linked to a recurring error that hasn't been
covered recently. If none of the major topics fit the recurring errors well
(e.g. the error is a small/idiomatic point like connector word choice, not
covered by the syllabus backbone), propose your own topic instead and mark
it as minor — do not force a poor-fitting major topic just to stay on the list.

If scope is "major", copy the `topic` string EXACTLY as it appears in the
curated list above (verbatim, character for character) — do not paraphrase,
shorten, or drop any part of it.

Return JSON only. No markdown.
{{
  "topic": "<exact curated topic string if major, or your own proposed topic if minor>",
  "difficulty": "<a1|a2|b1|b2>",
  "scope": "<major|minor>",
  "reason": "<why this topic, referencing the specific recurring error or its absence>"
}}"""
