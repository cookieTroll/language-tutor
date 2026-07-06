# Quick Start

The fastest path to a first session, plus the in-session commands and a suggested
first run-through. For provider switching (Ollama/Vertex), see [PROVIDERS.md](PROVIDERS.md).

## Not German?

The default config is tuned for German (A1–B2), the only hand-authored language.
Czech is also available (LLM-generated, native-speaker spot-checked). Any other
language falls back to generic defaults — usable, but lower feedback quality until
generated. See [Language Generation](README.md#language-generation) to add one:

```bash
export GEMINI_API_KEY=your-key-here
python -m scripts.generate_language french
```

If German (or Czech) is fine, skip straight to the commands below.

## Run it (default: Gemini)

```bash
git clone https://github.com/cookieTroll/language-tutor && cd language-tutor
pip install -e .
export GEMINI_API_KEY=your-key-here    # get one free at ai.google.dev
python -m ui.app                       # web UI, http://localhost:5000 — or: python -m ui.cli
```

Open `http://localhost:5000`, enter a user ID (any string; `student` if left blank), and
you'll land on the module-choice prompt.

## Commands

At the module-choice prompt:

| Input | Effect |
|---|---|
| Enter / `y` | Accept the suggested module |
| `writing` / `grammar` | Switch to that module instead |
| `/progress` | Mastery ratio per module + text-level trend |
| `/history` | Last 10 writing sessions summarised |
| `/history 5` | Last 5 sessions |
| `/history 7d` | Last 7 days |
| `/history 5 lang:german` | Same, reported in German instead of your explanation-language |
| `/language german` | Change your explanation-language setting itself |

Mid-writing-session, prefix a question with `/btw `:

```
/btw what does aufstehen mean?
```

The answer is shown inline and logged for vocab review — no need to leave the session.

## What to try first

1. Accept the default writing suggestion and submit a few sentences in your target
   language.
2. Read the evaluation: mistakes are tagged by severity against your CEFR level, with
   a corrected version and a summary.
3. Ask `/btw` about one word or phrase you weren't sure of while writing.
4. Run `/progress` to see the mastery view (empty on session one — this is the
   baseline).
5. Do 2–3 more writing sessions across a few days. Once an error tag recurs, the
   orchestrator will offer a grammar session on that exact topic at the next
   module-choice prompt — accept it to see the writing↔grammar bridge in action.
