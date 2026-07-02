"""Reusable seeding helpers for e2e / manual interactive testing.

Writes through the app's real StorageProtocol (write_user_profile, write_session,
write_file) so seeded fixtures are indistinguishable from real usage to the code
under test. Defaults to config.test.yaml's isolated data_root (data/test) so
seeded users never mix with real dev data and don't need manual cleanup.

Two kinds of fixtures:
  - seed_recurring_error(): synthetic error-tag history, for the writing<->grammar
    next_actions bridge (SessionManager._writing_error_recurrence_signal).
  - seed_writing_session() / seed_sample_writing_history(): realistic completed
    writing sessions (real user_text, varied topics) for components that read
    module history for content, not just error tags — topic_picker's recent-topic
    avoidance, recommend_exercise's aggregate stats, the session history view.
    Sample content comes from tests/longer texts/ (real prior German coursework).

Usable both as an import (from e2e tests) and as a standalone CLI script:

    python tests/e2e/seed_helpers.py recurring-error --user-id demo_user --tag verb_conjugation
    python tests/e2e/seed_helpers.py writing-history --user-id demo_user
"""
import argparse
import os
import re
import sys
import uuid
from datetime import datetime, timedelta

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config import load_config
from memory.factory import build_storage
from memory.protocols import UserProfile, SessionLog, WritingSessionContent

SAMPLE_TEXTS_DIR = os.path.join(PROJECT_ROOT, "tests", "longer texts")

# (filename, topic) for files that are a single completed writing task.
SINGLE_TEXT_SAMPLES = [
    ("Meinung_nach_essengewohnheiten.txt", "Meine Meinung zu Essgewohnheiten"),
    ("ausflug_cern.txt", "Ausflug nach CERN"),
    ("enschuldigen_dienstreise.txt", "Entschuldigung wegen einer Dienstreise"),
    ("note_son_sick.txt", "Entschuldigung: Kind krank"),
    ("vermissen_ersten_unterricht_email.txt", "E-Mail: ersten Unterricht verpasst"),
]

# monitor_gebrochen.txt bundles four distinct completed tasks, separated by a
# blank-blank-line gap — topics in file order.
MULTI_TEXT_SAMPLE = ("monitor_gebrochen.txt", [
    "Telefonat: kaputter Monitor reklamieren",
    "Telefonat: falsche Wäsche geliefert",
    "Bewerbung als Hausmeister",
    "Beschwerde: kaputtes Handy",
])


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "writing_practice"


def seed_recurring_error(
    user_id: str,
    tag: str,
    count: int = 2,
    language: str = "german",
    level: str = "a1",
    module: str = "writing",
    config_path: str = "config.test.yaml",
) -> dict[str, int]:
    """Seeds an active profile plus `count` completed sessions carrying `tag`.

    Mirrors SessionManager.RECURRING_ERROR_THRESHOLD's default (2) — pass a
    lower count to stay below the recurrence threshold, or higher to exceed it.
    Returns the resulting error_frequency for convenience/assertions.
    """
    config = load_config(config_path)
    store = build_storage(config)
    now = datetime.now()

    store.write_user_profile(UserProfile(
        user_id=user_id, language=language, level=level, level_source="stated",
        active=True, created_at=now, updated_at=now,
    ))

    for i in range(count):
        when = now - timedelta(days=i + 1)
        store.write_session(SessionLog(
            user_id=user_id, session_id=str(uuid.uuid4()), language=language, module=module,
            task_label=f"seed_{i}", task_description="seed", comment="seed session",
            errors=[{"error_tag": tag, "fragment": "seed fragment", "explanation": "seed mistake"}],
            level=level, date=when, file_path="", status="completed",
            started_at=when, completed_at=when + timedelta(minutes=5), duration_minutes=5.0,
        ))

    return store.get_error_frequency(user_id, language, module=module)


def seed_writing_session(
    user_id: str,
    text: str,
    topic: str,
    requirements: str = "",
    level: str = "b1",
    language: str = "german",
    mistakes: list[dict] | None = None,
    days_ago: int = 1,
    config_path: str = "config.test.yaml",
) -> str:
    """Seeds one completed writing session with real user_text — both the
    SessionLog DB row (for get_error_frequency/get_recent_sessions/aggregates)
    and the full WritingSessionContent YAML file (for the session history view).

    mistakes defaults to empty: this is about giving topic_picker/recommend_exercise
    realistic *content and topic variety* to read, not simulating full evaluator
    output — combine with seed_recurring_error() separately if a test also needs
    error-frequency history.

    Returns the seeded session_id.
    """
    config = load_config(config_path)
    store = build_storage(config)
    mistakes = mistakes or []
    now = datetime.now()
    when = now - timedelta(days=days_ago)
    session_id = str(uuid.uuid4())
    task_label = _slugify(topic)

    log = SessionLog(
        user_id=user_id, session_id=session_id, language=language, module="writing",
        task_label=task_label, task_description=topic, comment="seed session",
        errors=[
            {"error_tag": m["error_tag"], "fragment": m.get("fragment", ""), "explanation": m.get("explanation", "")}
            for m in mistakes
        ],
        level=level, date=when, file_path="", status="completed",
        started_at=when, completed_at=when + timedelta(minutes=15), duration_minutes=15.0,
    )
    store.write_session(log)

    content = WritingSessionContent(
        session_id=session_id, user_id=user_id, language=language, module="writing",
        task_label=task_label, date=when.strftime("%Y-%m-%dT%H:%M:%S"), level=level, status="completed",
        topic=topic, requirements=requirements, user_text=text,
        mistakes=mistakes, tips=[], corrected_text=text, session_summary="",
        btw_log=[], vocab_updates=[],
    )
    rel_path = store.write_file(content, config.data_root)
    log.file_path = rel_path
    store.write_session(log)

    return session_id


def seed_sample_writing_history(
    user_id: str,
    language: str = "german",
    level: str = "b1",
    config_path: str = "config.test.yaml",
) -> list[str]:
    """Seeds ~9 completed writing sessions from tests/longer texts/ (real prior
    German coursework) — varied topics/genres (opinion essay, travel narrative,
    informal excuse emails, formal complaint letters, a job application, phone-call
    transcripts) spread across the last several days. Also writes the active
    profile. Returns the seeded session_ids, oldest first.
    """
    config = load_config(config_path)
    store = build_storage(config)
    now = datetime.now()
    store.write_user_profile(UserProfile(
        user_id=user_id, language=language, level=level, level_source="stated",
        active=True, created_at=now, updated_at=now,
    ))

    tasks: list[tuple[str, str]] = []  # (topic, text)
    for filename, topic in SINGLE_TEXT_SAMPLES:
        with open(os.path.join(SAMPLE_TEXTS_DIR, filename), encoding="utf-8") as f:
            tasks.append((topic, f.read().strip()))

    multi_filename, multi_topics = MULTI_TEXT_SAMPLE
    with open(os.path.join(SAMPLE_TEXTS_DIR, multi_filename), encoding="utf-8") as f:
        parts = re.split(r"\n\s*\n\s*\n", f.read().strip())
    for topic, part in zip(multi_topics, parts):
        tasks.append((topic, part.strip()))

    session_ids = []
    total = len(tasks)
    for i, (topic, text) in enumerate(tasks):
        days_ago = total - i  # earliest task furthest in the past
        session_ids.append(seed_writing_session(
            user_id, text, topic, level=level, language=language,
            days_ago=days_ago, config_path=config_path,
        ))
    return session_ids


def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p1 = sub.add_parser("recurring-error", help="seed synthetic recurring-error history (writing<->grammar bridge)")
    p1.add_argument("--user-id", required=True)
    p1.add_argument("--tag", required=True, help="error_tag to seed, e.g. verb_conjugation")
    p1.add_argument("--count", type=int, default=2)
    p1.add_argument("--language", default="german")
    p1.add_argument("--level", default="a1")
    p1.add_argument("--module", default="writing")
    p1.add_argument("--config", default="config.test.yaml")

    p2 = sub.add_parser("writing-history", help="seed realistic writing sessions from tests/longer texts/")
    p2.add_argument("--user-id", required=True)
    p2.add_argument("--language", default="german")
    p2.add_argument("--level", default="b1")
    p2.add_argument("--config", default="config.test.yaml")

    args = parser.parse_args()

    if args.command == "recurring-error":
        freq = seed_recurring_error(
            args.user_id, args.tag, args.count, args.language, args.level, args.module, args.config,
        )
        print(f"Seeded '{args.user_id}' via {args.config}: error_frequency={freq}")
    elif args.command == "writing-history":
        session_ids = seed_sample_writing_history(args.user_id, args.language, args.level, args.config)
        print(f"Seeded '{args.user_id}' via {args.config}: {len(session_ids)} writing sessions")


if __name__ == "__main__":
    _main()
