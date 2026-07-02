import sys
import os

# Add the project root to sys.path so config and other top-level modules resolve correctly
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Windows cp1252 can't print box-drawing chars (──) or bullet points (•) used in evaluation output
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from config import load_config
from memory.factory import build_storage
from llm.factory import build_llm
from orchestrator.orchestrator import Orchestrator
from shared.io import TerminalIOHandler

def _language_config_warning(language: str, missing: list) -> None:
    print(f"\n[!] No language-specific configuration found for '{language.upper()}'.")
    print(f"    Falling back to generic defaults for: {', '.join(missing)}.")
    print(f"    To configure: add lang/languages/{language.lower()}.yaml and the referenced maps.")
    print( "    Feedback quality may be lower than with a language-specific setup.")
    try:
        input("\n    Press Enter to continue with defaults, or Ctrl+C to exit: ")
    except KeyboardInterrupt:
        print("\nExiting. Configure the language maps and restart.")
        raise


def main():
    if len(sys.argv) > 1:
        cmd = sys.argv[1].strip().lower()
        if cmd != "cli":
            print("Usage: ltut <command>\n")
            print("Commands:")
            print("  cli    Start the interactive local tutor console")
            return

    print("==================================================")
    print("          LANGUAGETUTOR - LOCAL POC TUI           ")
    print("==================================================")
    
    try:
        config_path = os.environ.get("LTUT_CONFIG", "config.yaml")
        config = load_config(config_path)
        store = build_storage(config)
        llm = build_llm(config.llm)
        
        if not llm.check_health():
            print(f"\n[!] ERROR: Cannot reach local LLM server at '{config.llm.base_url or 'http://localhost:1234/v1'}'.")
            print("    Please ensure LM Studio (or your local LLM provider) is running and the Local Server is enabled.")
            print("    If you want to use a cloud provider instead, update 'config.yaml' to use 'gemini'.\n")
            sys.exit(1)
            
        orchestrator = Orchestrator(store, llm, config, io=TerminalIOHandler())
    except Exception as e:
        print(f"[!] Error loading initialization layers: {e}")
        sys.exit(1)
        
    user_id = input("Enter your User ID [default: student]: ").strip()
    if not user_id:
        user_id = "student"
        
    forced_recommendation = None
    while True:
        try:
            # Run the full session flow (includes startup check, active language selection, etc.)
            forced_recommendation = orchestrator.run_session(
                user_id, language=None, on_language_warning=_language_config_warning,
                forced_recommendation=forced_recommendation,
            )
        except KeyboardInterrupt:
            print("\n\nExiting active tutoring session. Goodbye!")
            break
        except Exception as e:
            print(f"\n[!] An error occurred during the session: {e}")
            forced_recommendation = None

        if forced_recommendation is not None:
            continue

        again = input("\nStart another learning session? [Y/n]: ").strip().lower()
        if again == "n":
            print("Goodbye!")
            break

if __name__ == "__main__":
    main()
