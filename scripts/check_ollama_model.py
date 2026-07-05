"""Admin CLI: interactively ensures the Ollama model in the active config is ready.

Handles the cold-clone case ensure_ollama_ready() can't: config.yaml's default model
('gemma2-9b-tutor') doesn't exist until 'ollama create gemma2-9b-tutor -f Modelfile'
has been run once. This script checks the base model, the Modelfile, and the target
model, prompting for confirmation before pulling or creating anything.

Usage:
    python -m scripts.check_ollama_model
    python -m scripts.check_ollama_model --config config.test.yaml
"""

import argparse
import os
import subprocess
import sys

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from config import load_config
from llm.ollama_setup import _is_running, _wait_for_ollama, _local_models, _OLLAMA_API


def _read_modelfile_base(modelfile_path: str) -> str | None:
    with open(modelfile_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.upper().startswith("FROM "):
                return line.split(None, 1)[1].strip()
    return None


def _confirm(prompt: str) -> bool:
    return input(f"{prompt} [y/N] ").strip().lower() in ("y", "yes")


def _model_present(name: str, local: list[str]) -> bool:
    canonical = name if ":" in name else f"{name}:latest"
    return name in local or canonical in local


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=os.environ.get("LTUT_CONFIG", "config.yaml"))
    args = parser.parse_args()

    config = load_config(args.config)
    if config.llm.provider != "ollama":
        print(f"[!] '{args.config}' uses provider '{config.llm.provider}', not 'ollama'. Nothing to do.")
        return

    model = config.llm.model
    api_base = _OLLAMA_API
    if config.llm.base_url:
        api_base = config.llm.base_url.rstrip("/")
        if api_base.endswith("/v1"):
            api_base = api_base[:-3]

    if not _is_running(api_base):
        print("Ollama is not running. Starting it...")
        try:
            subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            print("[!] Ollama is not installed or not on PATH. Install from https://ollama.com.")
            sys.exit(1)
        if not _wait_for_ollama(api_base):
            print("[!] Ollama started but did not respond within 15 seconds.")
            sys.exit(1)

    local = _local_models(api_base)

    if _model_present(model, local):
        print(f"Model '{model}' is ready.")
        return

    modelfile_path = os.path.join(project_root, "Modelfile")
    if not os.path.isfile(modelfile_path):
        if not _confirm(f"Model '{model}' not found locally. Download it now?"):
            print("Aborted. Run this script again when you're ready.")
            sys.exit(1)
        result = subprocess.run(["ollama", "pull", model])
        if result.returncode != 0:
            print(f"[!] 'ollama pull {model}' failed with exit code {result.returncode}.")
            sys.exit(1)
        print(f"Model '{model}' ready.")
        return

    base_model = _read_modelfile_base(modelfile_path)
    if base_model and not _model_present(base_model, local):
        size_note = " (~5 GB)" if base_model.split(":")[0] in ("gemma2", "gemma") else ""
        if not _confirm(f"Base model '{base_model}'{size_note} not found. Download it now?"):
            print("Aborted. Run this script again when you're ready.")
            sys.exit(1)
        result = subprocess.run(["ollama", "pull", base_model])
        if result.returncode != 0:
            print(f"[!] 'ollama pull {base_model}' failed with exit code {result.returncode}.")
            sys.exit(1)
        local = _local_models(api_base)

    if not _confirm(f"Create '{model}' from {modelfile_path}?"):
        print("Aborted. Run this script again when you're ready.")
        sys.exit(1)
    result = subprocess.run(["ollama", "create", model, "-f", modelfile_path])
    if result.returncode != 0:
        print(f"[!] 'ollama create {model} -f {modelfile_path}' failed with exit code {result.returncode}.")
        sys.exit(1)
    print(f"Model '{model}' ready.")


if __name__ == "__main__":
    main()
