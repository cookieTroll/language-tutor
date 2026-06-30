SUMMARIZE_PROGRESS_PROMPT = """\
You are advising a language tutor on what to recommend next for a learner.

Learner level: {level}
Available modules: {modules}

Session history:
{session_lines}

Recurring errors (tag: count):
{error_lines}

Recent writing topics: {recent_topics}
Vocab flags: {vocab_flag_count}

Based on the above, identify the module the learner should focus on next and explain why in one sentence.

Return JSON only. No markdown, no preamble.
{{
  "weakest_module": "<one of the available modules>",
  "recommendation_reason": "<one sentence>"
}}
"""
