"""Prompt templates for lang/generate.py — LLM-assisted authoring of a new target
language's content maps (taxonomy, CEFR hints, grammar topics), matching the shape
lang/loader.py already validates for German.
"""

TAXONOMY_PROMPT = """You are designing an error-classification taxonomy for a {language} \
language-learning app, used to tag grammar/spelling/vocabulary mistakes made by learners \
of {language}.

Produce 6-10 tags covering the error categories a {language} learner actually makes \
(inflection, word order, agreement, tense/aspect, articles/case if applicable, spelling, \
vocabulary, etc. — whatever categories are linguistically relevant to {language} \
specifically, not a generic list). Each tag needs a concise English description a \
language model can act on when classifying a mistake.

You MUST include a tag named exactly "other" as a catch-all for errors that don't fit \
any other category.

Output ONLY raw YAML (no markdown fences, no commentary) in exactly this shape:

tags:
  some_tag_name: "Concise English description of what this covers"
  another_tag_name: "..."
  other: "Error does not clearly fit any category above — use as last resort"

Example shape (for a different language, illustrative only — invent tags that fit \
{language}, don't copy these):

tags:
  verb_conjugation: "Verb conjugation error — person/number agreement, tense marking"
  word_order: "Word order error — clause structure, phrase placement"
  article: "Article or determiner error"
  spelling: "Spelling error — accents, diacritics, orthography"
  vocabulary: "Wrong word choice, false friend, or register mismatch"
  other: "Error does not clearly fit any category above — use as last resort"
"""

CEFR_HINTS_PROMPT = """You are writing pedagogical focus hints for a {language} \
language-learning app, one per CEFR level (A1-C2), used to tell an LLM mistake-detector \
what kinds of errors to prioritize looking for at each level.

The app's error taxonomy for {language} uses exactly these tags:
{taxonomy_tags}

For each CEFR level (a1, a2, b1, b2, c1, c2), write one sentence naming which of the \
above tags are the priority focus at that level (progressing from basic to advanced), \
plus a "default" fallback sentence for when no level is known. Reference tags by their \
exact names from the list above.

Output ONLY raw YAML (no markdown fences, no commentary) in exactly this shape:

a1: "Focus on <tag>, <tag>, and basic vocabulary."
a2: "Focus on <tag>, <tag>, and <tag>."
b1: "Focus on <tag>, <tag>, and <tag>."
b2: "Focus on <tag>, <tag>, and vocabulary precision."
c1: "Focus on subtle vocabulary choices, register, and idiomatic usage."
c2: "Focus on register, stylistic nuance, and near-native correctness."
default: "Identify all grammatical, lexical, and spelling errors appropriate to the learner's level."
"""

GRAMMAR_TOPICS_PROMPT = """You are compiling a curated grammar syllabus for a {language} \
language-learning app, covering CEFR levels {level_low} through {level_high}.

The app's error taxonomy for {language} uses exactly these tags:
{taxonomy_tags}

Produce a flat list of major grammar topics a {language} course at these levels would \
cover (e.g. verb tenses, case/agreement systems, word order rules, articles — whatever is \
linguistically relevant to {language} specifically), ordered roughly by difficulty. \
Produce at least {min_topics} topics, spread across all requested levels.

Each topic needs:
- topic: short human-readable name
- difficulty: one of a1, a2, b1, b2, c1, c2 (must be within {level_low}-{level_high})
- scope: always the literal string "major"
- related_error_tags: a list of 1-3 tag names, EXACTLY matching names from the taxonomy \
list above — do not invent new tag names
- in_scope: 1-2 short phrases naming exactly what this topic covers
- out_of_scope: 1-2 short phrases naming closely-related things this topic does NOT cover \
(e.g. a related topic at a different level) — this disambiguates topics whose name alone \
is ambiguous

Output ONLY raw YAML (no markdown fences, no commentary), a flat list at the file root:

- topic: "Example topic name"
  difficulty: a1
  scope: major
  related_error_tags: ["some_tag_name"]
  in_scope:
    - "what this topic covers"
  out_of_scope:
    - "closely related thing this topic does NOT cover"
"""
