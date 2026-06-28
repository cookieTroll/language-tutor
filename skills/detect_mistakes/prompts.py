DETECT_MISTAKES_PROMPT = """You are evaluating a {level} {language} learner's writing.

Level guidance: {cefr_context}

Task given to the student:
{writing_prompt}

Known recurring errors to watch for:
{recurring_errors}

Student's text:
{user_text}

Identify all grammatical, vocabulary, and spelling errors.
Return JSON only. Provide the `error_type_hint` in English (e.g. "incorrect verb conjugation", "word order"). Format the response exactly as:
{{
  "mistakes": [
    {{"fragment": "user_fragment_here", "error_type_hint": "brief_description_here"}}
  ]
}}
If no errors are found, return an empty list:
{{
  "mistakes": []
}}
Do not write any markdown blocks, preamble, or explanation—only return valid JSON.
"""
