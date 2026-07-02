GENERIC_SCOPE_FALLBACK = (
    "If the topic name above contains a qualifier clause (specific verbs, "
    "\"regular\" vs \"irregular\", a named subset, etc.), treat that clause as "
    "a hard scope boundary — do not generalize beyond what it names."
)

DUMP_GRAMMAR_PROMPT = """\
You are a {language} grammar teacher writing a comprehensive explanation of:
"{topic}"

Target level: {level}

{scope_block}

Include:
- Core rule statement
- Full declension table or conjugation table if applicable
- Common cases and edge cases
- Common mistakes to avoid

MANDATORY — Examples section: include a dedicated "Examples" section with AT LEAST
4 example sentences (aim for 4-6), each one on its own line with its English
translation. Do not shorten this section or fold it into the rule discussion —
it must be a clearly separated, numbered or bulleted list of full sentences.
This is the most commonly skipped section, so do not omit or under-fill it.

Format as markdown. Be thorough — this is a reference explanation, not a quick note.
"""
