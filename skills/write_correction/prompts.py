WRITE_CORRECTION_PROMPT = """\
You are a {language} language teacher. A {level} learner has written the following text.
You have already identified and classified all mistakes. Your task now is to:

1. Produce a corrected version of the text by applying ONLY the listed corrections.
   Do NOT rephrase, restructure, or improve any part of the text that is not listed as a mistake.
2. Write 2–4 short, actionable recommendations the student should focus on going forward.
3. Write one encouraging sentence as an overall comment on the student's attempt.

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
