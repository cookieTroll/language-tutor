# LLM Provider Setup

## Switching providers

Select a provider by pointing `LTUT_CONFIG` at the matching config file:

```powershell
$env:LTUT_CONFIG = "config.gemini.yaml"
```

If `LTUT_CONFIG` is not set, `config.yaml` is used (currently: Ollama).

| Config file          | Provider       | Requires                                        |
|----------------------|----------------|-------------------------------------------------|
| `config.yaml`        | Ollama (local) | Ollama running, model pulled                    |
| `config.test.yaml`   | Ollama (local) | Same; writes to `data/test/`                    |
| `config.gemini.yaml` | Gemini API     | `GEMINI_API_KEY` env var                        |
| `config.vertex.yaml` | Vertex AI (ADC)| `GCP_PROJECT` + `GCP_REGION` env vars, `gcloud auth application-default login` |

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

`num_ctx: 2048` in `config.yaml` keeps the KV cache small enough for `gemma2:9b` to fit fully in 6 GB VRAM. Verify GPU utilisation after loading:

```powershell
ollama ps   # should show 100% GPU; if CPU% > 0, lower num_ctx further
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
# Ollama (default)
python -m ui.cli

# Gemini
$env:GEMINI_API_KEY = "your-key-here"
$env:LTUT_CONFIG = "config.gemini.yaml"
python -m ui.cli

# Vertex AI (uses your Google account via ADC — no API key)
# One-time setup:
#   gcloud auth application-default login
$env:GCP_PROJECT = "your-gcp-project-id"
$env:GCP_REGION  = "us-central1"
$env:LTUT_CONFIG = "config.vertex.yaml"
python -m ui.cli
```

### Web UI (Flask)

```powershell
# Ollama (default) — open http://localhost:5000 in a browser
python -m ui.app

# Gemini
$env:GEMINI_API_KEY = "your-key-here"
$env:LTUT_CONFIG = "config.gemini.yaml"
python -m ui.app

# Vertex AI
$env:GCP_PROJECT = "your-gcp-project-id"
$env:GCP_REGION  = "us-central1"
$env:LTUT_CONFIG = "config.vertex.yaml"
python -m ui.app
```

## Running judge tests

```powershell
# Ollama (default)
python -m pytest tests/judge/ -v -s

# Gemini
$env:GEMINI_API_KEY = "your-key-here"
$env:LTUT_CONFIG = "config.gemini.yaml"
python -m pytest tests/judge/ -v -s

# Vertex AI (uses your Google account via ADC — no API key)
# One-time setup:
#   gcloud auth application-default login
$env:GCP_PROJECT = "your-gcp-project-id"
$env:GCP_REGION  = "us-central1"
$env:LTUT_CONFIG = "config.vertex.yaml"
python -m pytest tests/judge/ -v -s
```

The judge also respects `LTUT_JUDGE_CONFIG` to use a different model for evaluation than for execution:

```powershell
# executor: Ollama, judge: Vertex AI
$env:GCP_PROJECT        = "your-gcp-project-id"
$env:GCP_REGION         = "us-central1"
$env:LTUT_JUDGE_CONFIG  = "config.vertex.yaml"
python -m pytest tests/judge/ -v -s
```
