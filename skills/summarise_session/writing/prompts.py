SUMMARISE_WRITING_SESSION_PROMPT = """You are assessing a {language} writing session for a {level} learner.

CEFR band descriptions:
{cefr_descriptors}

Text-level estimate (from independent CEFR assessment): {text_level_estimate}
The user's stated level is {level}.

Writing prompt given to the user:
{writing_prompt}

Mistakes identified in the user's writing (each includes "occurrence_count" — how many times that error_tag appears in this session):
{explained_mistakes}

Your task:

1. Assign a SEVERITY to each mistake. Use two factors:
   - How fundamental the error type is at {level}: critical = mastered long before this level; expected = still being learned; minor = beyond-level refinement
   - Frequency (occurrence_count): a single instance may be a slip; repeated errors with the same error_tag indicate a systematic gap and should be rated more critically

2. Write a SESSION SUMMARY: 1–2 holistic sentences assessing overall quality and level positioning.
   Example: "Strong B1 text approaching B2 range. Good fluency with occasional verb-placement errors typical for this stage."

3. Write 2–4 TIPS: forward-looking improvement suggestions ordered from near-level (what will help reach the next CEFR band) to aspirational (longer-term goals). Tips must NOT restate specific corrections — they should be actionable learning directions.

4. Set comparison_note to null.

Respond with exactly one JSON object:
{{
  "session_summary": "...",
  "mistakes": [
    {{
      "fragment": "...",
      "error_tag": "...",
      "correction": "...",
      "explanation": "...",
      "severity": "critical|expected|minor"
    }}
  ],
  "tips": ["...", "..."],
  "comparison_note": null
}}

The "mistakes" array must contain exactly the same mistakes as the input, in the same order, each enriched with a "severity" field."""
