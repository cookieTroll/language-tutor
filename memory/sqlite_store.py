import os
import sqlite3
import yaml
from datetime import datetime
from memory.protocols import (
    BaseSessionStore,
    SessionAggregate,
    SessionLog,
    BtwEntry,
    VocabFlag,
    UserProfile,
    SessionFileContent,
)

class SQLiteSessionStore(BaseSessionStore):
    def __init__(self, data_root: str):
        super().__init__(data_root)
        os.makedirs(self.data_root, exist_ok=True)
        # Create subdirectories for sessions, summaries, and checkpoints
        os.makedirs(os.path.join(self.data_root, "sessions"), exist_ok=True)
        os.makedirs(os.path.join(self.data_root, "summaries"), exist_ok=True)
        os.makedirs(os.path.join(self.data_root, "checkpoints"), exist_ok=True)
        
        self.db_path = os.path.join(self.data_root, "tutor.db")
        self._init_db()

    def _init_db(self):
        # Read and run memory/schema.sql
        schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
        with open(schema_path, "r", encoding="utf-8") as f:
            schema_sql = f.read()
            
        conn = sqlite3.connect(self.db_path)
        try:
            conn.executescript(schema_sql)
            # CREATE TABLE IF NOT EXISTS won't add columns to a table that already existed
            # before this field was introduced — migrate pre-existing local DBs in place.
            for ddl in (
                "ALTER TABLE sessions ADD COLUMN text_level_estimate TEXT",
                "ALTER TABLE sessions ADD COLUMN word_count INTEGER",
                "ALTER TABLE sessions ADD COLUMN score REAL",
            ):
                try:
                    conn.execute(ddl)
                except sqlite3.OperationalError:
                    pass  # column already present
            conn.commit()
        finally:
            conn.close()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _hydrate_session_log(self, row, conn, status_override: str | None = None) -> SessionLog:
        # Build a SessionLog from a sessions row + its errors. status_override lets
        # callers reclassify status (e.g. in_progress → interrupted) without a DB write.
        err_rows = conn.execute(
            "SELECT * FROM errors WHERE session_id = ?", (row["session_id"],)
        ).fetchall()
        errors = [
            {
                "error_tag": er["error_tag"],
                "fragment": er["source_text"],
                "correction": "",
                "explanation": er["error_detail"],
            }
            for er in err_rows
        ]
        return SessionLog(
            user_id=row["user_id"],
            session_id=row["session_id"],
            language=row["language"],
            module=row["module"],
            task_label=row["task_label"],
            task_description=row["task_description"],
            comment=row["comment"],
            errors=errors,
            level=row["level"],
            date=self._str_to_dt(row["date"]),
            file_path=row["file_path"],
            status=status_override if status_override is not None else row["status"],
            started_at=self._str_to_dt(row["started_at"]),
            completed_at=self._str_to_dt(row["completed_at"]),
            duration_minutes=row["duration_minutes"],
            text_level_estimate=row["text_level_estimate"],
            word_count=row["word_count"],
            score=row["score"],
        )

    # 1. write_session(self, log: SessionLog) -> None
    def write_session(self, log: SessionLog) -> None:
        conn = self._get_conn()
        try:
            # Check if session already exists
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM sessions WHERE session_id = ?", (log.session_id,))
            exists = cursor.fetchone() is not None
            
            if exists:
                conn.execute(
                    """
                    UPDATE sessions SET
                        user_id = ?, language = ?, module = ?, task_label = ?, task_description = ?,
                        comment = ?, level = ?, date = ?, file_path = ?, status = ?,
                        started_at = ?, completed_at = ?, duration_minutes = ?, text_level_estimate = ?,
                        word_count = ?, score = ?
                    WHERE session_id = ?
                    """,
                    (
                        log.user_id, log.language, log.module, log.task_label, log.task_description,
                        log.comment, log.level, self._dt_to_str(log.date), log.file_path, log.status,
                        self._dt_to_str(log.started_at), self._dt_to_str(log.completed_at), log.duration_minutes,
                        log.text_level_estimate, log.word_count, log.score, log.session_id
                    )
                )
            else:
                conn.execute(
                    """
                    INSERT INTO sessions (
                        session_id, user_id, language, module, task_label, task_description,
                        comment, level, date, file_path, status, started_at, completed_at, duration_minutes,
                        text_level_estimate, word_count, score
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        log.session_id, log.user_id, log.language, log.module, log.task_label, log.task_description,
                        log.comment, log.level, self._dt_to_str(log.date), log.file_path, log.status,
                        self._dt_to_str(log.started_at), self._dt_to_str(log.completed_at), log.duration_minutes,
                        log.text_level_estimate, log.word_count, log.score
                    )
                )
                
            # Insert or replace errors in errors table
            conn.execute("DELETE FROM errors WHERE session_id = ?", (log.session_id,))
            for err in log.errors:
                import uuid
                error_id = str(uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO errors (error_id, session_id, language, module, error_tag, error_detail, source_text)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        error_id, log.session_id, log.language, log.module, err["error_tag"],
                        err.get("error_detail") or err.get("explanation"),
                        err.get("source_text") or err.get("fragment")
                    )
                )
            conn.commit()
        finally:
            conn.close()

    def _update_session_status(self, session_id: str, status: str) -> None:
        conn = self._get_conn()
        try:
            conn.execute("UPDATE sessions SET status = ? WHERE session_id = ?", (status, session_id))
            conn.commit()
        finally:
            conn.close()

    # 4. get_recent_sessions
    def get_recent_sessions(self, user_id: str, language: str, n: int = 10) -> list[SessionLog]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """
                SELECT * FROM sessions 
                WHERE user_id = ? AND language = ?
                ORDER BY date DESC LIMIT ?
                """,
                (user_id, language, n)
            ).fetchall()
            
            return [self._hydrate_session_log(r, conn) for r in rows]
        finally:
            conn.close()

    # 5. get_sessions_by_module
    def get_sessions_by_module(self, user_id: str, language: str, module: str) -> list[SessionLog]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """
                SELECT * FROM sessions
                WHERE user_id = ? AND language = ? AND module = ?
                ORDER BY date DESC
                """,
                (user_id, language, module)
            ).fetchall()
            return [self._hydrate_session_log(r, conn) for r in rows]
        finally:
            conn.close()

    def get_session_by_id(self, session_id: str) -> SessionLog | None:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            return self._hydrate_session_log(row, conn) if row else None
        finally:
            conn.close()

    # 6. get_error_frequency
    def get_error_frequency(self, user_id: str, language: str, module: str | None = None) -> dict[str, int]:
        conn = self._get_conn()
        try:
            query = """
                SELECT e.error_tag, COUNT(*) as freq
                FROM errors e
                JOIN sessions s ON e.session_id = s.session_id
                WHERE s.user_id = ? AND s.language = ?
            """
            params: list = [user_id, language]
            if module:
                query += " AND e.module = ?"
                params.append(module)
            query += " GROUP BY e.error_tag"
            rows = conn.execute(query, params).fetchall()
            return {r["error_tag"]: r["freq"] for r in rows}
        finally:
            conn.close()

    # 7. get_recent_topics
    def get_recent_topics(self, user_id: str, language: str, module: str, n: int = 5) -> list[str]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """
                SELECT task_label FROM sessions
                WHERE user_id = ? AND language = ? AND module = ? AND status = 'completed'
                ORDER BY date DESC LIMIT ?
                """,
                (user_id, language, module, n)
            ).fetchall()
            return [r["task_label"] for r in rows]
        finally:
            conn.close()

    def get_session_aggregate(self, user_id: str, language: str) -> SessionAggregate:
        conn = self._get_conn()
        try:
            now = datetime.now()
            rows = conn.execute(
                """
                SELECT module,
                       COUNT(*) AS count,
                       MAX(completed_at) AS last_completed,
                       SUM(duration_minutes) AS total_minutes
                FROM sessions
                WHERE user_id = ? AND language = ? AND status = 'completed'
                GROUP BY module
                """,
                (user_id, language),
            ).fetchall()

            sessions_by_module: dict[str, int] = {}
            days_since_module: dict[str, float] = {}
            total_time_by_module: dict[str, float] = {}
            for r in rows:
                mod = r["module"]
                sessions_by_module[mod] = r["count"]
                total_time_by_module[mod] = float(r["total_minutes"] or 0)
                last_dt = self._str_to_dt(r["last_completed"])
                if last_dt:
                    days_since_module[mod] = (now - last_dt).total_seconds() / 86400.0

            error_freq = self.get_error_frequency(user_id, language)
            recurring_errors = [
                tag
                for tag, freq in sorted(error_freq.items(), key=lambda x: -x[1])
                if freq >= 2
            ]

            recent_topics = self.get_recent_topics(user_id, language, module="writing", n=5)

            vocab_row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM vocab_flags WHERE user_id = ? AND language = ?",
                (user_id, language),
            ).fetchone()
            vocab_flag_count = vocab_row["cnt"] if vocab_row else 0

            return SessionAggregate(
                sessions_by_module=sessions_by_module,
                days_since_module=days_since_module,
                total_time_by_module=total_time_by_module,
                recurring_errors=recurring_errors,
                recent_topics=recent_topics,
                vocab_flag_count=vocab_flag_count,
            )
        finally:
            conn.close()

    # 8. get_interrupted_sessions
    def get_interrupted_sessions(self, user_id: str, timeout_minutes: int) -> list[SessionLog]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM sessions WHERE user_id = ? AND status = 'in_progress'",
                (user_id,)
            ).fetchall()
            
            result = []
            now = datetime.now()
            for r in rows:
                started_at = self._str_to_dt(r["started_at"])
                if started_at:
                    elapsed = (now - started_at).total_seconds() / 60.0
                    if elapsed > timeout_minutes:
                        result.append(self._hydrate_session_log(r, conn, status_override="interrupted"))
            return result
        finally:
            conn.close()

    # 9. get_current_level
    def get_current_level(self, user_id: str) -> str:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT level FROM user_profiles WHERE user_id = ? AND active = 1",
                (user_id,)
            ).fetchone()
            if row:
                return row["level"]
            row_fallback = conn.execute(
                "SELECT level FROM user_profiles WHERE user_id = ? ORDER BY updated_at DESC LIMIT 1",
                (user_id,)
            ).fetchone()
            if row_fallback:
                return row_fallback["level"]
            return "a1"
        finally:
            conn.close()

    # 10. write_level
    def write_level(self, user_id: str, level: str, source: str) -> None:
        active_lang = self.get_active_language(user_id)
        if not active_lang:
            raise ValueError(f"No active language profile found for user {user_id} to write level to.")
            
        conn = self._get_conn()
        try:
            now_str = self._dt_to_str(datetime.now())
            conn.execute(
                """
                UPDATE user_profiles SET level = ?, level_source = ?, updated_at = ?
                WHERE user_id = ? AND language = ?
                """,
                (level, source, now_str, user_id, active_lang)
            )
            conn.commit()
        finally:
            conn.close()

    # 11. write_btw
    def write_btw(self, entry: BtwEntry) -> None:
        conn = self._get_conn()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO btw_log (btw_id, session_id, user_id, language, question, answer, flagged_word, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.btw_id, entry.session_id, entry.user_id, entry.language,
                    entry.question, entry.answer, entry.flagged_word, self._dt_to_str(entry.timestamp)
                )
            )
            conn.commit()
        finally:
            conn.close()

    # 12. get_btw_log
    def get_btw_log(self, user_id: str, language: str, session_id: str | None = None) -> list[BtwEntry]:
        conn = self._get_conn()
        try:
            if session_id:
                rows = conn.execute(
                    "SELECT * FROM btw_log WHERE user_id = ? AND language = ? AND session_id = ? ORDER BY timestamp ASC",
                    (user_id, language, session_id)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM btw_log WHERE user_id = ? AND language = ? ORDER BY timestamp ASC",
                    (user_id, language)
                ).fetchall()
                
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
                for r in rows
            ]
        finally:
            conn.close()

    # 13. get_vocab_flags
    def get_vocab_flags(self, user_id: str, language: str) -> list[VocabFlag]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM vocab_flags WHERE user_id = ? AND language = ? ORDER BY word ASC",
                (user_id, language)
            ).fetchall()
            
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
                for r in rows
            ]
        finally:
            conn.close()

    # 14. write_vocab_flag
    def write_vocab_flag(self, flag: VocabFlag) -> None:
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT flag_id, occurrence_count, first_seen FROM vocab_flags WHERE user_id = ? AND language = ? AND word = ?",
                (flag.user_id, flag.language, flag.word)
            )
            row = cursor.fetchone()
            
            now_str = self._dt_to_str(datetime.now())
            if row:
                new_count = row["occurrence_count"] + 1
                conn.execute(
                    """
                    UPDATE vocab_flags SET occurrence_count = ?, last_seen = ?, source = ?, translation = COALESCE(?, translation)
                    WHERE flag_id = ?
                    """,
                    (new_count, now_str, flag.source, flag.translation, row["flag_id"])
                )
            else:
                import uuid
                flag_id = flag.flag_id or str(uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO vocab_flags (flag_id, user_id, language, word, translation, source, first_seen, last_seen, occurrence_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        flag_id, flag.user_id, flag.language, flag.word, flag.translation,
                        flag.source, self._dt_to_str(flag.first_seen), self._dt_to_str(flag.last_seen), flag.occurrence_count
                    )
                )
            conn.commit()
        finally:
            conn.close()

    # 15. get_user_profile
    def get_user_profile(self, user_id: str, language: str) -> UserProfile | None:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM user_profiles WHERE user_id = ? AND language = ?",
                (user_id, language)
            ).fetchone()
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
        finally:
            conn.close()

    # 16. write_user_profile
    def write_user_profile(self, profile: UserProfile) -> None:
        conn = self._get_conn()
        try:
            if profile.active:
                conn.execute("UPDATE user_profiles SET active = 0 WHERE user_id = ?", (profile.user_id,))
                
            conn.execute(
                """
                INSERT INTO user_profiles (user_id, language, level, level_source, active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, language) DO UPDATE SET
                    level = excluded.level,
                    level_source = excluded.level_source,
                    active = excluded.active,
                    updated_at = excluded.updated_at
                """,
                (
                    profile.user_id, profile.language, profile.level, profile.level_source,
                    1 if profile.active else 0, self._dt_to_str(profile.created_at), self._dt_to_str(profile.updated_at)
                )
            )
            conn.commit()
        finally:
            conn.close()

    # 17. get_user_languages
    def get_user_languages(self, user_id: str) -> list[str]:
        conn = self._get_conn()
        try:
            rows = conn.execute("SELECT language FROM user_profiles WHERE user_id = ?", (user_id,)).fetchall()
            return [r["language"] for r in rows]
        finally:
            conn.close()

    # 18. get_active_language
    def get_active_language(self, user_id: str) -> str | None:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT language FROM user_profiles WHERE user_id = ? AND active = 1",
                (user_id,)
            ).fetchone()
            if row:
                return row["language"]
            return None
        finally:
            conn.close()

    # 19. list_users
    def list_users(self) -> list[str]:
        conn = self._get_conn()
        try:
            rows = conn.execute("SELECT DISTINCT user_id FROM user_profiles ORDER BY user_id").fetchall()
            return [r["user_id"] for r in rows]
        finally:
            conn.close()
