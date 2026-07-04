import re


def slugify_topic(topic: str) -> str:
    """Lossy, deterministic topic -> task_label slug. Used by both
    modules/grammar/agent.py (writing task_label at session time) and
    orchestrator/mastery.py (matching curated topic names back against stored
    task_labels) — must stay in sync between the two, hence shared here."""
    slug = re.sub(r"[^a-z0-9]+", "_", topic.lower()).strip("_")
    return slug or "grammar_practice"
