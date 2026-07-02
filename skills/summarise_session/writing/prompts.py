LOW_WORD_COUNT_WARNING = (
    "\n⚠ IMPORTANT: The student submitted only {word_count} words against a minimum of "
    "{min_words} required. You MUST flag this explicitly in the session_summary — "
    "do not praise the response without addressing its brevity.\n"
)

SUMMARISE_WRITING_SESSION_PROMPT = """You are assessing a {language} writing session for a {level} learner.

CEFR band descriptions:
{cefr_descriptors}

Text-level estimate (from independent CEFR assessment): {text_level_estimate}
The user's stated level is {level}.

Writing prompt given to the user:
{writing_prompt}

Student text ({word_count} words):
{user_text}
{low_word_count_warning}
Mistakes identified in the user's writing (each includes "occurrence_count" — how many times that error_tag appears in this session):
{explained_mistakes}

Your task:

1. Assign a SEVERITY to each mistake. Use two factors:
   - How fundamental the error type is at {level}: critical = mastered long before this level; expected = still being learned; minor = beyond-level refinement
   - Frequency (occurrence_count): a single instance may be a slip; repeated errors with the same error_tag indicate a systematic gap and should be rated more critically

2. Write a SESSION SUMMARY covering the following dimensions where relevant (use as many sentences as needed):
   - Task completion: did the student fully address the writing prompt? If the task was not fully completed, elaborate specifically on what was missing or left unaddressed.
   - Length: use the word count above as an objective reference — flag explicitly if the response is notably short relative to what the prompt called for (apply ~20% tolerance)
   - Accuracy: comment on error density relative to {level}
   - Fluency and coherence: does the text flow naturally and hold together logically?
   - Vocabulary range: is vocabulary appropriate and varied for {level}?
   Do NOT default to generic praise. If the text is minimal or has clear weaknesses, name them directly but constructively.

3. Write 2–4 TIPS ordered from near-level to aspirational:
   - Near-level tips must be grounded in the actual error_tags above or clearly observable characteristics of this text
   - Grammar topics fitting for the next CEFR band may be referenced in aspirational tips, even when not evidenced in this session's mistakes
   - Tips must NOT restate specific corrections — they should be actionable learning directions
   - Tips and session_summary must ALWAYS be written in English, regardless of the target language

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
  "tips": ["...", "..."]
}}

The "mistakes" array must contain exactly the same mistakes as the input, in the same order, each enriched with a "severity" field."""
