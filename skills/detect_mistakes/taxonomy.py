class TaxonomyError(ValueError):
    """Exception raised when an invalid error tag is encountered."""
    pass

ERROR_TAXONOMY: set[str] = {
    # Cases
    "dative_case", "accusative_case", "genitive_case",
    # Word order
    "word_order", "verb_position", "separable_verb",
    # Agreement
    "article_gender", "adjective_ending",
    # Verbs
    "verb_conjugation", "tense_usage",
    # Other
    "vocabulary", "spelling",
}

def validate_error_tag(tag: str) -> str:
    if tag not in ERROR_TAXONOMY:
        raise TaxonomyError(f"Unknown error_tag: '{tag}'. Must be one of {ERROR_TAXONOMY}")
    return tag
