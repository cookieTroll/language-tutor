# LanguageTutor — Language Architecture (`lang/`)

How target-language content is modeled, validated, and resolved at runtime. This is the
architecture doc; see `docs/lang_generation.md` for the LLM-driven tool that produces new
languages' content, and `docs/_contracts.md` for the raw Pydantic model definitions.

---

## Why this exists

Every skill and module needs language-specific reference content — an error taxonomy to
classify mistakes against, CEFR pedagogical hints, a grammar syllabus, exercise-type
vocabulary. Hardcoding any of this per-language into skill code would mean touching Python
every time a language is added or a taxonomy is revised. `lang/` exists to make that a
content change, not a code change.

---

## The six map types

Each is a versioned YAML file under `lang/maps/{concept}/`, validated through a Pydantic
model in `lang/models.py`, and resolved per-language via a name lookup in
`lang/languages/{language}.yaml`. Three are genuinely language-specific; three are
pedagogically universal and ship a single `default.yaml` that every language currently
points at.

| Map type | Model | Directory | Per-language or default? |
|---|---|---|---|
| CEFR hints | `CEFRMap` | `lang/maps/cefr/` | Language-specific — one pedagogical focus sentence per CEFR level (A1–C2 + `default`), naming which error tags matter most at that level |
| Error taxonomy | `TaxonomyMap` | `lang/maps/taxonomy/` | Language-specific — the tag vocabulary (`verb_conjugation`, `article`, ...) used to classify mistakes; always includes `other` as a catch-all, enforced by a model validator |
| Grammar topics | `GrammarTopicsMap` | `lang/maps/grammar_topics/` | Language-specific — the curated syllabus `select_grammar` picks from; each topic's `related_error_tags` is cross-checked against the taxonomy at load time |
| CEFR descriptors | `CEFRDescriptorMap` | `lang/maps/cefr_descriptors/` | Default only, today — CEFR is an international standard, so `default.yaml` covers text-level estimation without per-language content. Both German and Czech configs still point at `default` |
| Writing word ranges | `WritingMinWordsMap` | `lang/maps/writing_word_ranges/` | Default only, today — minimum word counts per level are pedagogically universal, not language-specific |
| Exercise types | `ExerciseTypesMap` | `lang/maps/exercise_types/` | Default only, today — the exercise-type vocabulary (`fill_in_the_blank`, `translation`, ...) for `generate_exercises` is pedagogically generic, kept in the same per-language-resolved pattern only so a future language *could* override the mix without touching skill code |

"Default only, today" is a statement about current content, not a limitation — the map
type is fully per-language-resolvable, nothing has just needed a language-specific
override yet.

---

## `LanguageConfig` — wiring a language together

`lang/languages/{name}.yaml` is a flat set of map-name references, one per concept:

```yaml
# lang/languages/german.yaml
name: german
cefr_hints: cefr_map1          # → lang/maps/cefr/cefr_map1.yaml
taxonomy: german_taxonomy_v1   # → lang/maps/taxonomy/german_taxonomy_v1.yaml
cefr_descriptors: default      # → lang/maps/cefr_descriptors/default.yaml
writing_word_ranges: default   # → lang/maps/writing_word_ranges/default.yaml
grammar_topics: german_a1_b2   # → lang/maps/grammar_topics/german_a1_b2.yaml
exercise_types: default        # → lang/maps/exercise_types/default.yaml
```

`grammar_topics` is the one field that can be `None` (a language with no grammar syllabus
yet still works for the writing module — grammar sessions just aren't available). Every
other field defaults to `"default"` if omitted. Adding a language is authoring this file
plus whichever maps aren't just pointing at `default` — no change to `lang/loader.py` or
`lang/models.py` is ever required.

---

## `_Registry` (`lang/loader.py`) — load-time cross-validation

A module-level `_Registry` instance loads every map file and every language config once,
at import time:

1. Globs each `lang/maps/{concept}/*.yaml`, validates it through the matching Pydantic
   model, and keys it by filename stem (e.g. `german_taxonomy_v1.yaml` → key
   `"german_taxonomy_v1"`).
2. Globs `lang/languages/*.yaml`, validates each as a `LanguageConfig`, then calls
   `_validate_references()` on it.

`_validate_references()` is the load-bearing part: it checks every map name a
`LanguageConfig` references actually exists (raising `ValueError` naming the missing map
and listing what *is* available), and additionally cross-checks every `GrammarTopic.
related_error_tags` entry against that language's own `TaxonomyMap.tag_set` — a grammar
topic can't reference an error tag that doesn't exist in the same language's taxonomy.
This is the same check `lang/generate.py`'s generation utility reuses (via a fresh
`_Registry` instance) to validate LLM-generated content end-to-end before writing it.

A bad reference fails at **startup**, not at the first session that happens to hit it —
the entire app refuses to boot with a language config pointing at a typo'd or missing map,
rather than surfacing a confusing `None` deep in a prompt template later.

---

## Public API (`lang/loader.py` module-level functions)

Everything else in the codebase goes through these, never through `_Registry` directly:

| Function | Returns |
|---|---|
| `get_cefr_context(language, level)` | Pedagogical focus hint string for this language/level |
| `get_taxonomy(language)` | `TaxonomyMap \| None` |
| `get_grammar_topics(language)` | `GrammarTopicsMap \| None` — `None` if the language has no grammar syllabus configured |
| `get_exercise_types(language)` | `ExerciseTypesMap \| None` |
| `get_cefr_descriptors(language)` | Formatted CEFR level-description table, for `estimate_text_level` prompts |
| `get_writing_min_words(language, level)` | `int` — minimum word count for a writing session at this level |
| `is_configured(language)` | `bool` — whether `lang/languages/{language}.yaml` exists at all |
| `using_defaults(language)` | `dict[str, bool]` — which of `cefr_hints`/`taxonomy` are resolving to the generic `default` map for this language |

Every getter falls back to that map type's `default.yaml` if the language isn't configured
or a specific map is missing — the app degrades gracefully to generic content rather than
crashing, while `is_configured()`/`using_defaults()` let the orchestrator warn the user
that feedback quality may be lower than with a language-specific setup (see
`orchestrator.py::_check_language_config`).

`is_configured()` vs `using_defaults()` answer different questions: a language can have a
config file (`is_configured() == True`) while some of its maps still point at `"default"`
(`using_defaults()` reports those as `True`) — that's the normal, expected state for
`cefr_descriptors`/`writing_word_ranges`/`exercise_types` on every language today, not a
degraded state.

---

## Adding a new language

Two paths, same destination (a `LanguageConfig` plus whatever maps it needs):

1. **Hand-author** — write the YAML files directly, following German's as a template.
2. **Generate** — `python -m scripts.generate_language <language>`, which produces all
   four files (taxonomy, CEFR hints, grammar topics, language config) via three chained,
   self-correcting LLM calls, validated through these exact same models and a fresh
   `_Registry` pass. See `docs/lang_generation.md` for how the generator works internally.
   Czech was produced this way.

Either way, nothing in `lang/loader.py` or `lang/models.py` changes — that's the entire
point of the versioned-map architecture.
