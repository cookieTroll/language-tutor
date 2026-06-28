CLASSIFY_MISTAKES_PROMPT = """\
You are evaluating a {level} {language} learner's writing mistakes.

Below is a list of raw mistakes detected in the student's text. For each mistake:
1. Choose the single best matching error_tag from the taxonomy below.
2. If the mistake does not clearly fit any specific tag, use "other".
3. Provide a minimal correction snippet — only fix the specific fragment, do not rewrite surrounding text.

Allowed error tags (use EXACTLY one of these strings — use "other" as a last resort):
{taxonomy}

Raw mistakes (JSON):
{raw_mistakes}

Return JSON only. No markdown, no preamble. Format:
{{
  "classified": [
    {{
      "fragment": "<original fragment from student text>",
      "error_tag": "<one tag from the taxonomy above>",
      "correction": "<minimal corrected version of the fragment>"
    }}
  ]
}}
If a mistake does not fit any taxonomy tag, omit it from the output.
"""
