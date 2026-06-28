ESTIMATE_TEXT_LEVEL_PROMPT = """You are assessing the CEFR proficiency level demonstrated in a {language} writing sample.

CEFR band descriptions:
{cefr_descriptors}

The user's stated level is {level} — use this as a reference point only. Your estimate must reflect the actual writing quality, not the stated level.

Writing prompt given to the user:
{writing_prompt}

User's response:
{user_text}

Respond with exactly one JSON object using lowercase CEFR bands.
If the response demonstrates assessable {language} writing, return:
  {{"text_level_estimate": "<band>"}}   where <band> is one of: a1 a2 b1 b2 c1 c2

If the text is too short, not in {language}, or contains no assessable language, return:
  {{"text_level_estimate": null}}"""
