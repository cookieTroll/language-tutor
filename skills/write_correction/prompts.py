WRITE_CORRECTION_PROMPT = """\
You are a {language} language teacher. A {level} learner has written the following text.
You have already identified and classified all mistakes. Your task now is to:

1. Produce a corrected version of the text by applying ONLY the listed corrections.
   Treat each correction as a literal substitution: find the exact fragment in the text and
   replace only those words — do not restructure any surrounding clause, and preserve
   {language}'s own word order conventions when the substitution is applied.
2. Write 2–4 short, actionable recommendations the student should focus on going forward,
   in {explanation_language}.
3. Write one encouraging sentence as an overall comment on the student's attempt,
   in {explanation_language}.

Original student text:
\"\"\"{user_text}\"\"\"

Mistakes with corrections (JSON):
{explained_mistakes}

Return JSON only. No markdown, no preamble. Format:
{{
  "corrected_text": "<full corrected version of the text>",
  "recommendations": [
    "<recommendation 1>",
    "<recommendation 2>"
  ],
  "comment": "<one encouraging sentence>"
}}
"""
