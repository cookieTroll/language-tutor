-- LanguageTutor SQLite Schema

CREATE TABLE IF NOT EXISTS user_profiles (
    user_id TEXT,
    language TEXT,
    level TEXT NOT NULL,
    level_source TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (user_id, language)
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    language TEXT NOT NULL,
    module TEXT NOT NULL,
    task_label TEXT NOT NULL,
    task_description TEXT NOT NULL,
    comment TEXT,
    level TEXT NOT NULL,
    date DATETIME NOT NULL,
    file_path TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at DATETIME,
    completed_at DATETIME,
    duration_minutes REAL,
    FOREIGN KEY (user_id, language) REFERENCES user_profiles (user_id, language)
);

CREATE INDEX IF NOT EXISTS idx_sessions_user_lang ON sessions (user_id, language);

CREATE TABLE IF NOT EXISTS errors (
    error_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    language TEXT NOT NULL,
    module TEXT NOT NULL,
    error_tag TEXT NOT NULL,
    error_detail TEXT,
    source_text TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions (session_id)
);

CREATE INDEX IF NOT EXISTS idx_errors_session ON errors (session_id);
CREATE INDEX IF NOT EXISTS idx_errors_lang ON errors (language);
CREATE INDEX IF NOT EXISTS idx_errors_module ON errors (module);

CREATE TABLE IF NOT EXISTS btw_log (
    btw_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    language TEXT NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    flagged_word TEXT,
    timestamp DATETIME NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions (session_id)
);

CREATE INDEX IF NOT EXISTS idx_btw_session ON btw_log (session_id);
CREATE INDEX IF NOT EXISTS idx_btw_user_lang ON btw_log (user_id, language);

CREATE TABLE IF NOT EXISTS vocab_flags (
    flag_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    language TEXT NOT NULL,
    word TEXT NOT NULL,
    translation TEXT,
    source TEXT NOT NULL,
    first_seen DATETIME NOT NULL,
    last_seen DATETIME NOT NULL,
    occurrence_count INTEGER NOT NULL DEFAULT 1,
    UNIQUE (user_id, language, word)
);

CREATE INDEX IF NOT EXISTS idx_vocab_flags_user_lang ON vocab_flags (user_id, language);
