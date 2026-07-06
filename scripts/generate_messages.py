"""Admin CLI: generates lang/messages/{language}.yaml (backend UI text catalog) for
a new explanation_language via LLM.

Usage:
    python -m scripts.generate_messages spanish
    python -m scripts.generate_messages spanish --force
"""

import argparse
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from config import load_config
from lang.generate_messages import generate_message_catalog, write_message_catalog
from lang.loader import is_message_catalog_configured
from llm.factory import build_llm


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("language", help="Explanation language, e.g. 'spanish'")
    parser.add_argument("--config", default=os.environ.get("LTUT_CONFIG", "config.yaml"))
    parser.add_argument(
        "--force", action="store_true",
        help="Overwrite an existing lang/messages/{language}.yaml if one already exists",
    )
    args = parser.parse_args()

    language = args.language.strip().lower()

    if is_message_catalog_configured(language) and not args.force:
        print(f"[!] '{language}' is already configured (lang/messages/{language}.yaml exists).")
        print("    Pass --force to regenerate and overwrite it.")
        sys.exit(1)

    config = load_config(args.config)
    llm = build_llm(config.llm)
    if not llm.check_health():
        print(f"[!] Cannot reach LLM backend '{config.llm.provider}'. Check config and try again.")
        sys.exit(1)

    print(f"Generating message catalog for '{language}'...")
    try:
        catalog = generate_message_catalog(llm, language)
        path = write_message_catalog(language, catalog)
    except Exception as e:
        print(f"[!] Generation failed: {e}")
        sys.exit(1)

    print(f"\nWritten: {path}")
    print(
        "\nReview the generated file before relying on it for real study sessions — "
        "an LLM translation should be checked for tone and accuracy, same as generated "
        "language content maps."
    )


if __name__ == "__main__":
    main()
