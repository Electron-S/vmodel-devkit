"""Sentence statistics: sentence count and average words per sentence."""

import re

_SENTENCE_RE = re.compile(r"([^.!?]*)([.!?]+)")


def sentence_stats(text: str) -> tuple[int, float]:
    """Return (sentence count, average words per sentence) for ``text``.

    A sentence is a segment ending in one or more of '.', '!' or '?' that
    contains at least one word. Unterminated trailing text is ignored.
    Raises TypeError if ``text`` is not a str.
    """
    if not isinstance(text, str):
        raise TypeError("text must be str, got " + type(text).__name__)
    count = 0
    total_words = 0
    for match in _SENTENCE_RE.finditer(text):
        words = len(match.group(1).split())
        if words:
            count += 1
            total_words += words
    if count == 0:
        return (0, 0.0)
    return (count, total_words / count)
