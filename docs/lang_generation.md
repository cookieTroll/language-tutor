# Wharf the Language Tutor — Language Asset Generation

How to add support for a new target language, and how the generator works internally.

See `docs/_contracts.md` for the underlying data shapes (`TaxonomyMap`, `CEFRMap`,
`GrammarTopicsMap`, `LanguageConfig`) and `lang/loader.py` for how they're resolved at
runtime.

---

## Why this exists

The `lang/` package was designed to be language-agnostic from the start: a target
language is just a `lang/languages/{name}.yaml` config file pointing at a handful of
versioned content maps under `lang/maps/`. Adding a new language never requires touching
loader or model code — only new content files in the same shape.

German is currently the only language with that content hand-authored
(`lang/maps/taxonomy/german_taxonomy_v1.yaml`, `lang/maps/cefr/cefr_map1.yaml`,
`lang/maps/grammar_topics/german_a1_b2.yaml`, `lang/languages/german.yaml`). Writing that
content by hand for every new language doesn't scale — `scripts/generate_language.py` uses
the LLM to draft it instead, validated through the exact same Pydantic contracts and
cross-reference checks the app already trusts for German.

---

## Running it

**Use a strong model for this.** In practice, generation quality was noticeably better
on hosted `gemini-2.5-flash` than on the local `gemma2:9b` default — this is worth the
hosted path even for users who otherwise run day-to-day study sessions locally. The
script defaults to `--config $LTUT_CONFIG` or `config.yaml` (Gemini), so set
`GEMINI_API_KEY` first or it will fail at the health check:

```bash
export GEMINI_API_KEY=your-key-here
python -m scripts.generate_language french
```

Options:

| Flag | Default | Meaning |
|---|---|---|
| `--config` | `$LTUT_CONFIG` or `config.yaml` | Which app config (and LLM backend) to use |
| `--level-range` | `a1-b2` | CEFR range the generated grammar syllabus should cover, e.g. `a1-b1` |
| `--force` | off | Overwrite an existing `lang/languages/{name}.yaml` instead of refusing |

The script reuses the same config/LLM wiring as `ui/cli.py` (`load_config`, `build_llm`,
a `check_health()` call before doing any generation work), so it respects whichever
provider (`gemini`, `ollama`, `openai_compat`, `vertex`) your `config.yaml` already points
at — no separate credentials or setup.

On success it prints the four files it wrote:

```
Written:
  taxonomy         -> lang/maps/taxonomy/french_taxonomy_v1.yaml
  cefr_hints       -> lang/maps/cefr/french_map1.yaml
  grammar_topics   -> lang/maps/grammar_topics/french_a1_b2.yaml
  language_config  -> lang/languages/french.yaml
```

**Review the output before relying on it for real study sessions.** An LLM-authored
curriculum should get the same scrutiny the hand-curated German one did (see the review
note at the top of `lang/maps/grammar_topics/german_a1_b2.yaml`) — spot-check tag
assignments and grammar-topic scoping for linguistic accuracy, the same way you'd review
any AI-drafted content before shipping it.

---

## What it generates

Four files, mirroring the German pattern exactly:

1. **Taxonomy** (`lang/maps/taxonomy/{name}_taxonomy_v1.yaml`) — the error-tag vocabulary
   used to classify learner mistakes for this language (e.g. `verb_conjugation`,
   `word_order`, `article`). Always includes `other` as a catch-all — enforced by
   `TaxonomyMap`'s own validator, the same one German's file satisfies.
2. **CEFR hints** (`lang/maps/cefr/{name}_map1.yaml`) — one pedagogical focus sentence per
   CEFR level (A1–C2 plus a `default`), naming which of the taxonomy's tags matter most at
   that level. Grounded in the taxonomy generated in step 1, so hints only ever reference
   tags that actually exist.
3. **Grammar topics** (`lang/maps/grammar_topics/{name}_a1_b2.yaml`) — the curated syllabus
   `select_grammar` picks topics from, each tagged with `related_error_tags` cross-checked
   against the taxonomy, plus `in_scope`/`out_of_scope` boundaries (see the `GrammarTopic`
   docstring in `lang/models.py` for why that boundary matters — `dump_grammar` and
   `generate_exercises` are independent LLM calls given only the topic name, and can
   silently drift apart on scope without it).
4. **Language config** (`lang/languages/{name}.yaml`) — wires the three maps above
   together. `cefr_descriptors`, `writing_word_ranges`, and `exercise_types` are left as
   `"default"` — those three are already language-agnostic (CEFR is an international
   standard, exercise types are pedagogically universal), so there's nothing
   language-specific to generate for them.

---

## How it works internally (`lang/generate.py`)

Three LLM calls, strictly in this order — each one's output feeds the next, so later
steps can only ever reference tags/names that were actually generated, never invented
independently:

```
generate_taxonomy(llm, language)
        │
        ▼  (taxonomy.tag_set)
generate_cefr_hints(llm, language, taxonomy)
        │
        ▼  (taxonomy.tag_set)
generate_grammar_topics(llm, language, taxonomy, level_range)
        │
        ▼
write_language_assets(name, taxonomy, cefr_hints, grammar_topics)
```

Each generator calls `skills.protocols.call_with_self_correction` — the same
LLM-call-with-retry helper `generate_exercises` and other skills already use — with a
`parse_fn` that:

1. Strips markdown code fences if the model wrapped its YAML in them.
2. Parses via `yaml.safe_load` and validates through the existing Pydantic model
   (`TaxonomyMap`, `CEFRMap`, or `GrammarTopicsMap` — no new validation logic was
   written; these are the exact same models `lang/loader.py` validates German against).
3. For grammar topics specifically, additionally checks every `related_error_tags` entry
   against the just-generated taxonomy's tag set — mirroring the check
   `lang/loader.py::_validate_references` runs at app startup — so a hallucinated tag
   name triggers a self-correction retry immediately instead of surfacing as a load-time
   error later.

If validation fails, `call_with_self_correction` feeds the error back to the model and
retries (up to `config.yaml`'s `llm.max_skill_retries`, default 3) before giving up.

`write_language_assets()` serializes each validated model back to YAML (not the model's
raw text response — guarantees consistent formatting), writes the four files, and then,
as a final end-to-end check, constructs a **fresh** `lang.loader._Registry` pointed at the
real `lang/maps`/`lang/languages` directories. That registry re-parses everything from
disk and raises `ValueError` on any bad cross-reference — the exact same validation the
app already runs at import time, reused as-is rather than duplicated.

---

## What happens when a user picks an unconfigured language

Previously, selecting a language with no `lang/languages/{name}.yaml` silently fell back
to the generic default maps (see `lang/loader.py::using_defaults`) with a vague "falling
back to defaults" warning. Now the warning path (`orchestrator.py::_check_language_config`
→ `on_language_warning` callback, wired in both `ui/cli.py` and `ui/app.py`)
distinguishes the two cases via `lang.loader.is_configured()`:

- **No config file at all** (`is_configured() == False`) — tells the user the language
  isn't supported yet and to run `python -m scripts.generate_language <language>`.
- **Config file exists but some maps are still `"default"`** (`is_configured() == True`,
  some `using_defaults()` entries `True`) — the original "falling back to generic
  defaults" message, unchanged.

---

## Message catalog generation (`scripts/generate_messages.py`)

A separate, smaller generator for `lang/messages/{language}.yaml` (see `docs/lang.md`'s
"Message catalog" section for the loader/model side) — resolved by
`explanation_language`, not the target study language, so it's a distinct script
rather than another step chained into `generate_language`.

Same model caveat as `generate_language` above — prefer hosted Gemini for translation
quality, and set `GEMINI_API_KEY` first since this script also defaults to
`config.yaml`:

```bash
export GEMINI_API_KEY=your-key-here
python -m scripts.generate_messages spanish
python -m scripts.generate_messages spanish --force
```

`lang/generate_messages.py::generate_message_catalog` sends the LLM the full
`lang/messages/default.yaml` id→template mapping and asks for a translation, then
(inside the `call_with_self_correction` `parse_fn`, same retry helper
`lang/generate.py` uses) checks two things before accepting the response:

1. **Id completeness** — `MessageCatalog`'s own validator, same `REQUIRED_MESSAGE_IDS`
   check the app applies to every catalog at load time.
2. **Placeholder preservation** — every `{placeholder}` token in each id's default
   template must appear, verbatim, in the translated template (checked via regex-extracted
   placeholder sets, exact match required). This is the load-bearing check: a translation
   that drops or mistranslates a `{level}`/`{module}`/etc. token would `KeyError` at
   runtime the next time the app calls `.format()` on it, not at generation time,
   without this — the same class of bug the taxonomy tag cross-check in
   `generate_grammar_topics` exists to catch early instead of late.

`write_message_catalog()` writes `lang/messages/{language}.yaml` and re-validates by
re-parsing the written file through `MessageCatalog.model_validate` — no cross-file
references to check here (unlike `write_language_assets`), so a reparse is sufficient.

**Review the output before relying on it**, same as the language-content generator —
tone and idiom accuracy for backend UI copy is not something id-completeness or
placeholder checks can verify.

---

## Non-goals

This utility (`generate_language`) only generates the LLM-facing content maps —
taxonomy, CEFR hints, grammar topics, language config. Localizing the app's own
backend-generated text (orchestrator menus, confirmations, status lines) is a
**separate** generator, `generate_messages` (above) — the two are deliberately not
chained together since they resolve by different axes (target language vs.
explanation language). Neither generator makes web UI changes; the "Fully Configurable
Origin / Target / Communication Languages" entry in `docs/_CHECKLIST.md` (modeling a
distinct origin/native-language concept, exposing the languages catalog to the
selection flow) remains open.

---

## Tests

`tests/unit/lang/test_generate.py` — mocked-LLM coverage: happy-path parse/validate for
each generator, self-correction retry when a generated grammar topic references an
unknown taxonomy tag or a CEFR level comes back empty, and a `write_language_assets`
round-trip through a fresh `_Registry` at `tmp_path` (both the success case and a
deliberately-broken cross-reference that must raise).

`tests/unit/lang/test_generate_messages.py` — same shape for the message-catalog
generator: happy-path translation preserving placeholders, self-correction retry when a
placeholder is dropped, gives up after `max_skill_retries` on a persistent mismatch, and
a `write_message_catalog` round-trip through a reparse.

No judge/live-LLM test exists for output *quality* (curriculum accuracy, tag
appropriateness, or — for the message catalog — translation tone) — that's what the
manual review step above is for, the same way the hand-authored German curriculum was
manually reviewed before use.
