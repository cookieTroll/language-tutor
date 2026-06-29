import json
import subprocess
import time
import urllib.request


_OLLAMA_API = "http://localhost:11434"


def _is_running(base: str = _OLLAMA_API) -> bool:
    try:
        with urllib.request.urlopen(f"{base}/api/tags", timeout=1.5) as r:
            return r.status == 200
    except Exception:
        return False


def _wait_for_ollama(base: str = _OLLAMA_API, timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _is_running(base):
            return True
        time.sleep(0.5)
    return False


def _local_models(base: str = _OLLAMA_API) -> list[str]:
    with urllib.request.urlopen(f"{base}/api/tags", timeout=5.0) as r:
        data = json.loads(r.read())
    return [m["name"] for m in data.get("models", [])]


def ensure_ollama_ready(model: str, base_url: str | None = None) -> None:
    """
    Ensures Ollama is running and the requested model is available locally.
    Starts Ollama if not running; pulls the model if not present.
    Raises RuntimeError on failure.
    """
    # Derive the native Ollama API base from the OpenAI-compat base_url if given
    # (strip the /v1 suffix, since Ollama's own API lives at the root)
    api_base = _OLLAMA_API
    if base_url:
        api_base = base_url.rstrip("/")
        if api_base.endswith("/v1"):
            api_base = api_base[:-3]

    if not _is_running(api_base):
        try:
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            raise RuntimeError(
                "Ollama is not installed or not on PATH. "
                "Install from https://ollama.com and run 'ollama serve'."
            )
        print("Starting Ollama...", flush=True)
        if not _wait_for_ollama(api_base):
            raise RuntimeError("Ollama started but did not respond within 15 seconds.")

    try:
        local = _local_models(api_base)
    except Exception as e:
        raise RuntimeError(f"Could not query Ollama model list: {e}") from e

    # Ollama tags models as 'name:latest' if no tag given
    canonical = model if ":" in model else f"{model}:latest"
    if model not in local and canonical not in local:
        print(f"Pulling Ollama model '{model}' (this may take a while)...", flush=True)
        result = subprocess.run(["ollama", "pull", model])
        if result.returncode != 0:
            raise RuntimeError(f"'ollama pull {model}' failed with exit code {result.returncode}.")
        print(f"Model '{model}' ready.", flush=True)
