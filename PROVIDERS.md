# LLM Provider Setup

> All commands below use PowerShell (`$env:VAR = "value"`). On macOS/Linux, use
> `export VAR=value` instead.

## Switching providers

Select a provider by pointing `LTUT_CONFIG` at the matching config file:

```powershell
$env:LTUT_CONFIG = "config.gemini.yaml"
```

If `LTUT_CONFIG` is not set, `config.yaml` is used (currently: Gemini).

| Config file          | Provider       | Requires                                        |
|----------------------|----------------|-------------------------------------------------|
| `config.yaml`        | Gemini (hosted)| `GEMINI_API_KEY` env var — identical to `config.gemini.yaml`, kept as the default alias |
| `config.ollama.yaml` | Ollama (local) | Ollama running, custom model built (see below)  |
| `config.test.yaml`   | Ollama (local) | Same; writes to `data/test/`                    |
| `config.gemini.yaml` | Gemini API     | `GEMINI_API_KEY` env var                        |
| `config.vertex.yaml` | Vertex AI (ADC)| `GCP_PROJECT` env var (+ optional `GCP_REGION`), `gcloud auth application-default login` |

Prefer to run fully local and free instead? Point `LTUT_CONFIG` at `config.ollama.yaml`
— see the Ollama setup section below.

---

## Ollama: custom model setup

`config.ollama.yaml`'s `llm.model` is `gemma2-9b-tutor` — a **custom** Ollama model, not
a stock one, so a plain `ollama pull gemma2-9b-tutor` will not work. It's built locally
from the `Modelfile` at the repo root (`FROM gemma2:9b`, tuned `num_ctx`/stop tokens)
via:

```powershell
ollama create gemma2-9b-tutor -f Modelfile
```

That requires the base `gemma2:9b` model to be pulled first. Rather than doing this by
hand, run the helper script, which checks for the custom model, pulls the base model if
needed, and runs `ollama create` for you:

```powershell
python -m scripts.check_ollama_model
```

This is a one-time, first-run step (also called out in README.md's quickstart).

---

## Ollama performance (6 GB GPU)

Set `OLLAMA_FLASH_ATTENTION` before launching the app — the app auto-starts Ollama if it isn't running yet, so the flag just needs to be in the same terminal session:

```powershell
$env:OLLAMA_FLASH_ATTENTION = "1"
python -m ui.app
```

If Ollama is already running (started without the flag), restart it first:

```powershell
$env:OLLAMA_FLASH_ATTENTION = "1"
ollama serve
```

`num_ctx: 4096` in `config.yaml` keeps the KV cache small enough for `gemma2-9b-tutor` (based on `gemma2:9b`) to fit fully in 6 GB VRAM. Verify GPU utilisation after loading:

```powershell
ollama ps   # should show 100% GPU; if CPU% > 0, lower num_ctx below 4096
```

---

## API keys

Keys are never stored in config files. The config references them via `${VAR_NAME}` placeholders resolved at load time.

Set for the current terminal session only (disappears on close):

```powershell
$env:GEMINI_API_KEY = "your-key-here"
```

---

## Running the app

### CLI

```powershell
# Gemini (default)
$env:GEMINI_API_KEY = "your-key-here"
python -m ui.cli

# Ollama (free, fully local)
$env:LTUT_CONFIG = "config.ollama.yaml"
python -m ui.cli

# Vertex AI (uses your Google account via ADC — no API key)
# One-time setup:
#   pip install google-cloud-aiplatform
#   gcloud auth application-default login
$env:GCP_PROJECT = "your-gcp-project-id"
$env:GCP_REGION  = "europe-west1"   # optional; defaults to europe-west1 if unset
$env:LTUT_CONFIG = "config.vertex.yaml"
python -m ui.cli
```

### Web UI (Flask)

```powershell
# Gemini (default) — open http://localhost:5000 in a browser
$env:GEMINI_API_KEY = "your-key-here"
python -m ui.app

# Ollama (free, fully local)
$env:LTUT_CONFIG = "config.ollama.yaml"
python -m ui.app

# Vertex AI
$env:GCP_PROJECT = "your-gcp-project-id"
$env:GCP_REGION  = "europe-west1"   # optional; defaults to europe-west1 if unset
$env:LTUT_CONFIG = "config.vertex.yaml"
python -m ui.app
```

## Running judge tests

```powershell
# Ollama
$env:LTUT_CONFIG = "config.ollama.yaml"
python -m pytest tests/judge/ -v -s

# Gemini
$env:GEMINI_API_KEY = "your-key-here"
$env:LTUT_CONFIG = "config.gemini.yaml"
python -m pytest tests/judge/ -v -s

# Vertex AI (uses your Google account via ADC — no API key)
# One-time setup:
#   pip install google-cloud-aiplatform
#   gcloud auth application-default login
$env:GCP_PROJECT = "your-gcp-project-id"
$env:GCP_REGION  = "europe-west1"   # optional; defaults to europe-west1 if unset
$env:LTUT_CONFIG = "config.vertex.yaml"
python -m pytest tests/judge/ -v -s
```

The judge also respects `LTUT_JUDGE_CONFIG` to use a different model for evaluation than for execution:

```powershell
# executor: Ollama, judge: Vertex AI
$env:GCP_PROJECT        = "your-gcp-project-id"
$env:GCP_REGION         = "europe-west1"   # optional; defaults to europe-west1 if unset
$env:LTUT_JUDGE_CONFIG  = "config.vertex.yaml"
python -m pytest tests/judge/ -v -s
```
