VERIFY_MISTAKES_PROMPT = """\
You are proofreading a list of candidate errors flagged by an earlier, less careful
pass over a {language} learner's writing. Your only job here is to confirm or reject
each candidate — do not invent new errors, do not correct anything, do not classify
anything.

Full student text (for context):
\"\"\"{user_text}\"\"\"

Candidate errors (JSON):
{raw_mistakes}

For each candidate, find its fragment in the text above and judge it in its real
sentence context: is this fragment DEFINITELY grammatically, lexically, or
orthographically wrong — not just unusual, informal, or simply not how you
personally would phrase it?

Rules:
- Reject (keep=false) anything that is actually correct once checked against its real
  sentence context — including word order that looks unusual in isolation but is
  required by a grammar rule (e.g. verb-second inversion after a fronted adverb or
  connector like "deshalb", "dann", "trotzdem").
- Keep (keep=true) only fragments that are genuinely, objectively wrong.
- Do not change the fragment text and do not add or drop candidates — return a
  verdict for every single candidate in the list above, nothing more and nothing less.
- If unsure, keep it (a later step re-examines it) — only reject what you are
  confident is actually correct {language}.

Return JSON only, no markdown, no explanation:
{{
  "verified": [
    {{"fragment": "<exact fragment from the candidate list>", "keep": true}}
  ]
}}"""
