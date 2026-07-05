from shared.humanize import humanize_tag


def test_replaces_underscores_and_title_cases():
    assert humanize_tag("verb_conjugation") == "Verb Conjugation"


def test_single_word_tag():
    assert humanize_tag("other") == "Other"


def test_empty_string_passthrough():
    assert humanize_tag("") == ""
