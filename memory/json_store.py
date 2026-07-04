import os
import json
import yaml
from datetime import datetime
from memory.protocols import (
    BaseSessionStore,
    SessionLog,
    BtwEntry,
    VocabFlag,
    UserProfile,
    SessionFileContent,
)

class JSONSessionStore(BaseSessionStore):
    def __init__(self, data_root: str):
        super().__init__(data_root)
        self.store_dir = os.path.join(self.data_root, "json_store")
        os.makedirs(self.store_dir, exist_ok=True)
        os.makedirs(os.path.join(self.data_root, "sessions"), exist_ok=True)
        os.makedirs(os.path.join(self.data_root, "summaries"), exist_ok=True)
        os.makedirs(os.path.join(self.data_root, "checkpoints"), exist_ok=True)
        
        self.sessions_file = os.path.join(self.store_dir, "sessions.json")
        self.profiles_file = os.path.join(self.store_dir, "profiles.json")
        self.errors_file = os.path.join(self.store_dir, "errors.json")
        self.btw_file = os.path.join(self.store_dir, "btw.json")
        self.vocab_file = os.path.join(self.store_dir, "vocab.json")
        
        self._init_files()

    def _init_files(self):
        for f in (self.sessions_file, self.profiles_file, self.errors_file, self.btw_file, self.vocab_file):
            if not os.path.exists(f):
                with open(f, "w", encoding="utf-8") as file:
                    json.dump({}, file)

    def _read(self, path: str) -> dict:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _write(self, path: str, data: dict):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    # 1. write_session
    def write_session(self, log: SessionLog) -> None:
        sessions = self._read(self.sessions_file)
        sessions[log.session_id] = {
            "session_id": log.session_id,
            "user_id": log.user_id,
            "language": log.language,
            "module": log.module,
            "task_label": log.task_label,
            "task_description": log.task_description,
            "comment": log.comment,
            "level": log.level,
            "date": self._dt_to_str(log.date),
            "file_path": log.file_path,
            "status": log.status,
            "started_at": self._dt_to_str(log.started_at),
            "completed_at": self._dt_to_str(log.completed_at),
            "duration_minutes": log.duration_minutes,
            "text_level_estimate": log.text_level_estimate,
        }
        self._write(self.sessions_file, sessions)

        # Update errors
        errors = self._read(self.errors_file)
        # Clear existing errors for this session
        to_delete = [k for k, v in errors.items() if v["session_id"] == log.session_id]
        for k in to_delete:
            del errors[k]
            
        for i, err in enumerate(log.errors):
            import uuid
            err_id = str(uuid.uuid4())
            errors[err_id] = {
                "error_id": err_id,
                "session_id": log.session_id,
                "language": log.language,
                "module": log.module,
                "error_tag": err["error_tag"],
                "error_detail": err.get("explanation") or err.get("error_detail"),
                "source_text": err.get("fragment") or err.get("source_text"),
            }
        self._write(self.errors_file, errors)

    def _update_session_status(self, session_id: str, status: str) -> None:
        sessions = self._read(self.sessions_file)
        if session_id in sessions:
            sessions[session_id]["status"] = status
            self._write(self.sessions_file, sessions)

    # 4. get_recent_sessions
    def get_recent_sessions(self, user_id: str, language: str, n: int = 10) -> list[SessionLog]:
        sessions = self._read(self.sessions_file)
        errors = self._read(self.errors_file)
        
        filtered = [
            v for v in sessions.values()
            if v["user_id"] == user_id and v["language"] == language
        ]
        # Sort descending by date
        filtered.sort(key=lambda x: x["date"], reverse=True)
        recent = filtered[:n]
        
        result = []
        for r in recent:
            sess_errors = [
                {"error_tag": ev["error_tag"], "fragment": ev["source_text"], "correction": "", "explanation": ev["error_detail"]}
                for ev in errors.values() if ev["session_id"] == r["session_id"]
            ]
            result.append(
                SessionLog(
                    user_id=r["user_id"],
                    session_id=r["session_id"],
                    language=r["language"],
                    module=r["module"],
                    task_label=r["task_label"],
                    task_description=r["task_description"],
                    comment=r["comment"],
                    errors=sess_errors,
                    level=r["level"],
                    date=self._str_to_dt(r["date"]),
                    file_path=r["file_path"],
                    status=r["status"],
                    started_at=self._str_to_dt(r["started_at"]),
                    completed_at=self._str_to_dt(r["completed_at"]),
                    duration_minutes=r["duration_minutes"],
                    text_level_estimate=r.get("text_level_estimate"),
                )
            )
        return result

    # 5. get_sessions_by_module
    def get_sessions_by_module(self, user_id: str, language: str, module: str) -> list[SessionLog]:
        sessions = self._read(self.sessions_file)
        errors = self._read(self.errors_file)
        
        filtered = [
            v for v in sessions.values()
            if v["user_id"] == user_id and v["language"] == language and v["module"] == module
        ]
        filtered.sort(key=lambda x: x["date"], reverse=True)
        
        result = []
        for r in filtered:
            sess_errors = [
                {"error_tag": ev["error_tag"], "fragment": ev["source_text"], "correction": "", "explanation": ev["error_detail"]}
                for ev in errors.values() if ev["session_id"] == r["session_id"]
            ]
            result.append(
                SessionLog(
                    user_id=r["user_id"],
                    session_id=r["session_id"],
                    language=r["language"],
                    module=r["module"],
                    task_label=r["task_label"],
                    task_description=r["task_description"],
                    comment=r["comment"],
                    errors=sess_errors,
                    level=r["level"],
                    date=self._str_to_dt(r["date"]),
                    file_path=r["file_path"],
                    status=r["status"],
                    started_at=self._str_to_dt(r["started_at"]),
                    completed_at=self._str_to_dt(r["completed_at"]),
                    duration_minutes=r["duration_minutes"],
                    text_level_estimate=r.get("text_level_estimate"),
                )
            )
        return result

    def get_session_by_id(self, session_id: str) -> SessionLog | None:
        sessions = self._read(self.sessions_file)
        r = sessions.get(session_id)
        if not r:
            return None
        errors = self._read(self.errors_file)
        sess_errors = [
            {"error_tag": ev["error_tag"], "fragment": ev["source_text"], "correction": "", "explanation": ev["error_detail"]}
            for ev in errors.values() if ev["session_id"] == session_id
        ]
        return SessionLog(
            user_id=r["user_id"],
            session_id=r["session_id"],
            language=r["language"],
            module=r["module"],
            task_label=r["task_label"],
            task_description=r["task_description"],
            comment=r["comment"],
            errors=sess_errors,
            level=r["level"],
            date=self._str_to_dt(r["date"]),
            file_path=r["file_path"],
            status=r["status"],
            started_at=self._str_to_dt(r["started_at"]),
            completed_at=self._str_to_dt(r["completed_at"]),
            duration_minutes=r["duration_minutes"],
            text_level_estimate=r.get("text_level_estimate"),
        )

    # 6. get_error_frequency
    def get_error_frequency(self, user_id: str, language: str, module: str | None = None) -> dict[str, int]:
        sessions = self._read(self.sessions_file)
        errors = self._read(self.errors_file)
        
        freq = {}
        for ev in errors.values():
            sess = sessions.get(ev["session_id"])
            if sess and sess["user_id"] == user_id and sess["language"] == language:
                if module is None or ev.get("module") == module:
                    tag = ev["error_tag"]
                    freq[tag] = freq.get(tag, 0) + 1
        return freq

    # 7. get_recent_topics
    def get_recent_topics(self, user_id: str, language: str, module: str, n: int = 5) -> list[str]:
        sessions = self._read(self.sessions_file)
        filtered = [
            v for v in sessions.values()
            if v["user_id"] == user_id and v["language"] == language and v["module"] == module and v["status"] == "completed"
        ]
        filtered.sort(key=lambda x: x["date"], reverse=True)
        return [r["task_label"] for r in filtered[:n]]

    # 8. get_interrupted_sessions
    def get_interrupted_sessions(self, user_id: str, timeout_minutes: int) -> list[SessionLog]:
        sessions = self._read(self.sessions_file)
        errors = self._read(self.errors_file)
        
        filtered = [
            v for v in sessions.values()
            if v["user_id"] == user_id and v["status"] == "in_progress"
        ]
        
        result = []
        now = datetime.now()
        for r in filtered:
            started_at = self._str_to_dt(r["started_at"])
            if started_at:
                elapsed = (now - started_at).total_seconds() / 60.0
                if elapsed > timeout_minutes:
                    sess_errors = [
                        {"error_tag": ev["error_tag"], "fragment": ev["source_text"], "correction": "", "explanation": ev["error_detail"]}
                        for ev in errors.values() if ev["session_id"] == r["session_id"]
                    ]
                    result.append(
                        SessionLog(
                            user_id=r["user_id"],
                            session_id=r["session_id"],
                            language=r["language"],
                            module=r["module"],
                            task_label=r["task_label"],
                            task_description=r["task_description"],
                            comment=r["comment"],
                            errors=sess_errors,
                            level=r["level"],
                            date=self._str_to_dt(r["date"]),
                            file_path=r["file_path"],
                            status="interrupted",
                            started_at=started_at,
                            completed_at=self._str_to_dt(r["completed_at"]),
                            duration_minutes=r["duration_minutes"],
                            text_level_estimate=r.get("text_level_estimate"),
                        )
                    )
        return result

    # 9. get_current_level
    def get_current_level(self, user_id: str) -> str:
        profiles = self._read(self.profiles_file)
        # Find active profile
        user_profs = [v for v in profiles.values() if v["user_id"] == user_id]
        active = [v for v in user_profs if v["active"]]
        if active:
            return active[0]["level"]
        # Fallback
        if user_profs:
            user_profs.sort(key=lambda x: x["updated_at"], reverse=True)
            return user_profs[0]["level"]
        return "a1"

    # 10. write_level
    def write_level(self, user_id: str, level: str, source: str) -> None:
        active_lang = self.get_active_language(user_id)
        if not active_lang:
            raise ValueError(f"No active language profile found for user {user_id} to write level to.")
            
        profiles = self._read(self.profiles_file)
        key = f"{user_id}:{active_lang}"
        if key in profiles:
            profiles[key]["level"] = level
            profiles[key]["level_source"] = source
            profiles[key]["updated_at"] = self._dt_to_str(datetime.now())
            self._write(self.profiles_file, profiles)

    # 11. write_btw
    def write_btw(self, entry: BtwEntry) -> None:
        btws = self._read(self.btw_file)
        btws[entry.btw_id] = {
            "btw_id": entry.btw_id,
            "session_id": entry.session_id,
            "user_id": entry.user_id,
            "language": entry.language,
            "question": entry.question,
            "answer": entry.answer,
            "flagged_word": entry.flagged_word,
            "timestamp": self._dt_to_str(entry.timestamp)
        }
        self._write(self.btw_file, btws)

    # 12. get_btw_log
    def get_btw_log(self, user_id: str, language: str, session_id: str | None = None) -> list[BtwEntry]:
        btws = self._read(self.btw_file)
        filtered = [
            v for v in btws.values()
            if v["user_id"] == user_id and v["language"] == language
        ]
        if session_id:
            filtered = [v for v in filtered if v["session_id"] == session_id]
            
        filtered.sort(key=lambda x: x["timestamp"])
        return [
            BtwEntry(
                btw_id=r["btw_id"],
                session_id=r["session_id"],
                user_id=r["user_id"],
                language=r["language"],
                question=r["question"],
                answer=r["answer"],
                flagged_word=r["flagged_word"],
                timestamp=self._str_to_dt(r["timestamp"])
            )
            for r in filtered
        ]

    # 13. get_vocab_flags
    def get_vocab_flags(self, user_id: str, language: str) -> list[VocabFlag]:
        vocab = self._read(self.vocab_file)
        filtered = [
            v for v in vocab.values()
            if v["user_id"] == user_id and v["language"] == language
        ]
        filtered.sort(key=lambda x: x["word"])
        return [
            VocabFlag(
                flag_id=r["flag_id"],
                user_id=r["user_id"],
                language=r["language"],
                word=r["word"],
                translation=r["translation"],
                source=r["source"],
                first_seen=self._str_to_dt(r["first_seen"]),
                last_seen=self._str_to_dt(r["last_seen"]),
                occurrence_count=r["occurrence_count"]
            )
            for r in filtered
        ]

    # 14. write_vocab_flag
    def write_vocab_flag(self, flag: VocabFlag) -> None:
        vocab = self._read(self.vocab_file)
        
        # Check unique constraint (user_id, language, word)
        existing_key = None
        for k, v in vocab.items():
            if v["user_id"] == flag.user_id and v["language"] == flag.language and v["word"] == flag.word:
                existing_key = k
                break
                
        now_str = self._dt_to_str(datetime.now())
        if existing_key:
            vocab[existing_key]["occurrence_count"] += 1
            vocab[existing_key]["last_seen"] = now_str
            vocab[existing_key]["source"] = flag.source
            if flag.translation:
                vocab[existing_key]["translation"] = flag.translation
        else:
            import uuid
            flag_id = flag.flag_id or str(uuid.uuid4())
            vocab[flag_id] = {
                "flag_id": flag_id,
                "user_id": flag.user_id,
                "language": flag.language,
                "word": flag.word,
                "translation": flag.translation,
                "source": flag.source,
                "first_seen": self._dt_to_str(flag.first_seen),
                "last_seen": self._dt_to_str(flag.last_seen),
                "occurrence_count": flag.occurrence_count
            }
        self._write(self.vocab_file, vocab)

    # 15. get_user_profile
    def get_user_profile(self, user_id: str, language: str) -> UserProfile | None:
        profiles = self._read(self.profiles_file)
        key = f"{user_id}:{language}"
        row = profiles.get(key)
        if row:
            return UserProfile(
                user_id=row["user_id"],
                language=row["language"],
                level=row["level"],
                level_source=row["level_source"],
                active=bool(row["active"]),
                created_at=self._str_to_dt(row["created_at"]),
                updated_at=self._str_to_dt(row["updated_at"])
            )
        return None

    # 16. write_user_profile
    def write_user_profile(self, profile: UserProfile) -> None:
        profiles = self._read(self.profiles_file)
        if profile.active:
            for k in profiles:
                if profiles[k]["user_id"] == profile.user_id:
                    profiles[k]["active"] = False
                    
        key = f"{profile.user_id}:{profile.language}"
        profiles[key] = {
            "user_id": profile.user_id,
            "language": profile.language,
            "level": profile.level,
            "level_source": profile.level_source,
            "active": True if profile.active else False,
            "created_at": self._dt_to_str(profile.created_at),
            "updated_at": self._dt_to_str(profile.updated_at)
        }
        self._write(self.profiles_file, profiles)

    # 17. get_user_languages
    def get_user_languages(self, user_id: str) -> list[str]:
        profiles = self._read(self.profiles_file)
        return [v["language"] for v in profiles.values() if v["user_id"] == user_id]

    # 18. get_active_language
    def get_active_language(self, user_id: str) -> str | None:
        profiles = self._read(self.profiles_file)
        active = [v["language"] for v in profiles.values() if v["user_id"] == user_id and v["active"]]
        return active[0] if active else None

    # 19. list_users
    def list_users(self) -> list[str]:
        profiles = self._read(self.profiles_file)
        return sorted({v["user_id"] for v in profiles.values()})
