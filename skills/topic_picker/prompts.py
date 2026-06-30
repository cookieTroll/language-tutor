TOPIC_PICKER_PROMPT = """\
You are assigning a {level} {language} writing exercise.

Learner context:
- Recent topics to AVOID repeating: {recent_topics}
- Recurring error tags to STEER toward: {error_tags}
- Suggested focus from tutor: {suggested_focus}
- Minimum word count: {min_words}

Choose a realistic, engaging topic appropriate for {level} level. If a suggested focus or \
recurring errors are provided, weave a relevant requirement into the task (e.g. "use at least \
two dative prepositions" for dative_case errors). Do not repeat a recent topic.

Return JSON only. No markdown.
{{
  "topic": "<one sentence describing the writing scenario>",
  "requirements": "<2-3 concrete requirements, including 'minimum {min_words} words'>",
  "task_label": "<short_underscore_slug e.g. daily_routine>"
}}"""
