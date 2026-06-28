import sys
from config import load_config
from memory.factory import build_storage
from llm.factory import build_llm
from orchestrator.orchestrator import Orchestrator

def main():
    print("==================================================")
    print("          LANGUAGETUTOR - LOCAL POC TUI           ")
    print("==================================================")
    
    try:
        config = load_config()
        store = build_storage(config)
        llm = build_llm(config.llm)
        
        if not llm.check_health():
            print(f"\n[!] ERROR: Cannot reach local LLM server at '{config.llm.base_url or 'http://localhost:1234/v1'}'.")
            print("    Please ensure LM Studio (or your local LLM provider) is running and the Local Server is enabled.")
            print("    If you want to use a cloud provider instead, update 'config.yaml' to use 'gemini'.\n")
            sys.exit(1)
            
        orchestrator = Orchestrator(store, llm, config)
    except Exception as e:
        print(f"[!] Error loading initialization layers: {e}")
        sys.exit(1)
        
    user_id = input("Enter your User ID [default: student]: ").strip()
    if not user_id:
        user_id = "student"
        
    while True:
        try:
            # Run the full session flow (includes startup check, active language selection, etc.)
            orchestrator.run_session(user_id, language=None)
        except KeyboardInterrupt:
            print("\n\nExiting active tutoring session. Goodbye!")
            break
        except Exception as e:
            print(f"\n[!] An error occurred during the session: {e}")
            
        again = input("\nStart another learning session? [Y/n]: ").strip().lower()
        if again == "n":
            print("Goodbye!")
            break

if __name__ == "__main__":
    main()
