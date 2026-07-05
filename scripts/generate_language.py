"""Admin CLI: generates lang/ content maps for a new target language via LLM.

Usage:
    python -m scripts.generate_language french
    python -m scripts.generate_language french --level-range a1-b1 --force
"""

import argparse
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from config import load_config
from lang.generate import generate_language
from lang.loader import is_configured
from llm.factory import build_llm


def _parse_level_range(value: str) -> tuple[str, str]:
    parts = value.lower().split("-")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(f"Expected LOW-HIGH (e.g. a1-b2), got '{value}'")
    valid = {"a1", "a2", "b1", "b2", "c1", "c2"}
    low, high = parts
    if low not in valid or high not in valid:
        raise argparse.ArgumentTypeError(f"Levels must be one of {sorted(valid)}, got '{value}'")
    return low, high


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("language", help="Target language name, e.g. 'french'")
    parser.add_argument("--config", default=os.environ.get("LTUT_CONFIG", "config.yaml"))
    parser.add_argument(
        "--level-range", type=_parse_level_range, default=("a1", "b2"),
        help="CEFR range for the grammar syllabus, e.g. a1-b2 (default) or a1-b1",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Overwrite an existing lang/languages/{language}.yaml if one already exists",
    )
    args = parser.parse_args()

    language = args.language.strip().lower()

    if is_configured(language) and not args.force:
        print(f"[!] '{language}' is already configured (lang/languages/{language}.yaml exists).")
        print("    Pass --force to regenerate and overwrite it.")
        sys.exit(1)

    config = load_config(args.config)
    llm = build_llm(config.llm)
    if not llm.check_health():
        print(f"[!] Cannot reach LLM backend '{config.llm.provider}'. Check config and try again.")
        sys.exit(1)

    print(f"Generating language assets for '{language}' ({args.level_range[0]}-{args.level_range[1]})...")
    try:
        paths = generate_language(language, llm, level_range=args.level_range)
    except Exception as e:
        print(f"[!] Generation failed: {e}")
        sys.exit(1)

    print("\nWritten:")
    for label, path in paths.items():
        print(f"  {label:16s} -> {path}")
    print(
        "\nReview the generated files before relying on them for real study sessions — "
        "an LLM-authored curriculum should be checked for linguistic accuracy, same as "
        "the hand-curated German one was."
    )


if __name__ == "__main__":
    main()
