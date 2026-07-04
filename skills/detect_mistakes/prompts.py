DETECT_MISTAKES_PROMPT = """You are evaluating a {level} {language} learner's writing.

Level guidance: {cefr_context}

Task given to the student:
{writing_prompt}

Known recurring errors to watch for:
{recurring_errors}

Student's text:
{user_text}

Identify genuine grammatical, vocabulary, and spelling errors — things that are objectively wrong and have a specific correction.

Go sentence by sentence, and within each sentence check ALL of these categories
independently, even after you've already found an error in that sentence or a
nearby one: verb conjugation/tense/auxiliary, noun-adjective agreement (gender,
case, number), article/case, word order, spelling. A single sentence can contain
more than one unrelated error (e.g. a wrong verb conjugation AND a wrong adjective
ending in the same sentence), and two consecutive sentences can each contain a
different kind of error. Finding one or two obvious errors (like a wrong verb form)
does not mean the scan is done — do not stop early, and do not let an obvious error
in one sentence distract you from checking the sentence right after it just as
carefully.

Rules:
- Only flag text that is definitively incorrect. If a sentence is grammatically correct, do not flag it even if it sounds simple or unusual.
- Do not flag style, register, or idiomatic preferences — only objective errors.
- fragment must be the shortest phrase that contains the error, not the whole sentence.
- For verb errors (wrong auxiliary, wrong form, separable verb not split, wrong tense), include the full verb expression in the fragment — e.g. both the auxiliary and the participle, or the subject pronoun with the finite verb.
- error_type_hint must name the specific grammatical problem in English (e.g. "separable verb not split", "verb-second word order violated", "wrong dative inflection after mit", "wrong Perfekt auxiliary for motion verb").
- If the text contains no errors, return an empty mistakes list. Do not invent errors. When in doubt, do not flag.

Return JSON only, no markdown, no explanation:
{{
  "mistakes": [
    {{"fragment": "shortest_erroneous_phrase", "error_type_hint": "specific_problem"}}
  ]
}}
If no errors:
{{
  "mistakes": []
}}"""
