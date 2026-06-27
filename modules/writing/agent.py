import uuid
import time
import threading
import sys
from datetime import datetime
from modules.protocols import ModuleProtocol, ContextRequest, ModuleContext, ModuleResult
from memory.protocols import WritingSessionContent, BtwEntry
from llm.base import BaseLLM
from skills.protocols import SkillInput
from modules.writing.skills import get_writing_skills

class SessionTimer:
    def __init__(self):
        self._running = False
        self._thread = None
        self._start_time = None

    def start(self):
        self._running = True
        self._start_time = time.time()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
        # Reset window title
        sys.stdout.write("\x1b]2;LanguageTutor\x07")
        sys.stdout.flush()

    def _run(self):
        while self._running:
            elapsed = time.time() - self._start_time
            minutes = int(elapsed // 60)
            seconds = int(elapsed % 60)
            title = f"LanguageTutor - [{minutes:02d}:{seconds:02d} elapsed]"
            sys.stdout.write(f"\x1b]2;{title}\x07")
            sys.stdout.flush()
            time.sleep(1.0)

class WritingModule(ModuleProtocol):
    name = "writing"
    description = "Conducts a German writing session. Generates a prompt at the user's level, accepts their written response, identifies grammar and vocabulary errors, provides structured feedback with explanations, and produces a corrected version."

    def __init__(self):
        self.skills = get_writing_skills()

    def context_request(self) -> ContextRequest:
        return ContextRequest(
            recent_sessions_n=5,
            module_filter="writing",
            include_error_frequency=True,
            include_recent_topics=True,
            include_vocab_flags=True,
        )

    def run(
        self, ctx: ModuleContext, llm: BaseLLM
    ) -> tuple[ModuleResult, WritingSessionContent]:
        session_id = str(uuid.uuid4())
        started_at = datetime.now()

        # 1. Topic definition (PoC: hardcoded)
        topic = "Describe your morning routine"
        requirements = "150-200 words, use Perfekt tense, include 3 separable verbs"
        writing_prompt = f"Topic: {topic}\nRequirements: {requirements}"

        print("\n==================================================")
        print("           GERMAN WRITING EXERCISE")
        print("==================================================")
        print(f"Target Level: {ctx.level.upper()}")
        print(f"Topic: {topic}")
        print(f"Requirements: {requirements}")
        print("--------------------------------------------------")
        print("Type your text below. To submit, type an empty line.")
        print("To ask a question mid-writing, prefix it with '/btw ' (e.g. /btw what does aufstehen mean?).")
        print("==================================================\n")

        user_lines = []
        btw_entries = []
        vocab_signals = []

        first_interaction = True

        timer = SessionTimer()
        timer.start()

        while True:
            try:
                line = input("> ").strip()
            except EOFError:
                break

            if first_interaction:
                started_at = datetime.now()
                first_interaction = False

            # Check for /btw question
            if line.startswith("/btw "):
                question = line[5:].strip()
                print(f"[*] Asking tutor: '{question}'...")
                
                session_context = {
                    "module": self.name,
                    "topic": topic,
                    "user_text_so_far": "\n".join(user_lines),
                    "level": ctx.level
                }
                
                btw_skill = self.skills["btw_handler"]
                btw_input = SkillInput(
                    user_id=ctx.user_id,
                    level=ctx.level,
                    parameters={"question": question, "session_context": session_context}
                )
                
                output = btw_skill.run(btw_input, llm)
                answer = output.metadata.get("answer", "No answer received.")
                flagged_word = output.metadata.get("flagged_word")
                
                print(f"\nTutor: {answer}\n")
                
                btw_entry_id = str(uuid.uuid4())
                btw_entries.append(
                    BtwEntry(
                        btw_id=btw_entry_id,
                        session_id=session_id,
                        user_id=ctx.user_id,
                        language=ctx.language,
                        question=question,
                        answer=answer,
                        flagged_word=flagged_word,
                        timestamp=datetime.now()
                    )
                )
                if flagged_word:
                    vocab_signals.append(flagged_word)
                continue

            # Check if user typed "/end" or submitted an empty line
            if line == "/end" or line == "":
                if not user_lines:
                    print("Please write some text before submitting!")
                    continue
                break

            user_lines.append(line)

        timer.stop()
        user_text = "\n".join(user_lines)
        print("\n[*] Evaluating your text. Please wait...")

        # 4. Invoke detect_mistakes skill
        detector = self.skills["detect_mistakes"]
        detector_input = SkillInput(
            user_id=ctx.user_id,
            level=ctx.level,
            parameters={
                "user_text": user_text,
                "writing_prompt": writing_prompt,
                "recurring_errors": list(ctx.error_frequency.keys())
            }
        )
        detector_output = detector.run(detector_input, llm)
        raw_mistakes = detector_output.metadata.get("raw_mistakes", [])

        # Display raw mistakes to user
        print("\n==================================================")
        print("                 EVALUATION")
        print("==================================================")
        if detector_output.success and raw_mistakes:
            print(f"Found {len(raw_mistakes)} potential mistakes:")
            for i, m in enumerate(raw_mistakes, 1):
                print(f"{i}. Fragment: '{m['fragment']}'")
                print(f"   Hint: {m['error_type_hint']}")
        elif not detector_output.success:
            print("[!] Mistake detection failed.")
            print(f"    Error: {detector_output.metadata.get('error', 'Unknown error')}")
        else:
            print("Excellent! No mistakes were identified.")
        print("==================================================\n")

        completed_at = datetime.now()
        duration_minutes = (completed_at - started_at).total_seconds() / 60.0

        errors = [
            {
                "error_tag": "vocabulary" if "vocab" in m.get("error_type_hint", "").lower() else "grammar",
                "fragment": m["fragment"],
                "explanation": m["error_type_hint"]
            }
            for m in raw_mistakes
        ]

        session_content = WritingSessionContent(
            session_id=session_id,
            user_id=ctx.user_id,
            language=ctx.language,
            module=self.name,
            task_label="writing_free",
            date=started_at.strftime("%Y-%m-%dT%H:%M:%S"),
            level=ctx.level,
            status="completed",
            topic=topic,
            requirements=requirements,
            user_text=user_text,
            mistakes=[
                {
                    "error_tag": "spelling" if "spell" in m.get("error_type_hint", "").lower() else "grammar",
                    "fragment": m["fragment"],
                    "correction": "",
                    "explanation": m["error_type_hint"]
                }
                for m in raw_mistakes
            ],
            recommendations=["Focus on practicing separable verbs.", "Pay attention to sentence structure."],
            corrected_text=user_text,
            comment="Session completed successfully in PoC mode.",
            btw_log=[
                {
                    "question": e.question,
                    "answer": e.answer,
                    "flagged_word": e.flagged_word,
                    "timestamp": e.timestamp.strftime("%Y-%m-%dT%H:%M:%S")
                }
                for e in btw_entries
            ],
            vocab_updates=[
                {"word": word, "source": "btw", "occurrence_count": 1}
                for word in vocab_signals
            ],
            suggested_focus=None
        )

        result = ModuleResult(
            session_id=session_id,
            module=self.name,
            task_label="writing_free",
            task_description=writing_prompt,
            errors=errors,
            comment="Completed in PoC mode.",
            started_at=started_at,
            completed_at=completed_at,
            duration_minutes=duration_minutes,
            metadata={
                "btw_entries": btw_entries,
                "vocab_signals": vocab_signals
            }
        )

        return result, session_content
