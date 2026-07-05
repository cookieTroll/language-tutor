def humanize_tag(tag: str) -> str:
    """Learner-facing label for a taxonomy/error tag name, e.g. 'verb_conjugation'
    -> 'Verb Conjugation'. Display-only — never write this back over the raw tag,
    which stays the key used for error_frequency aggregation, taxonomy validation,
    and grammar-topic matching."""
    if not tag:
        return tag
    return tag.replace("_", " ").strip().title()
