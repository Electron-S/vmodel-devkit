"""Word frequency (DESIGN-002, DESIGN-003)."""
from collections import Counter

from textstats.tokenizer import tokenize


def count_words(text: str) -> dict[str, int]:
    return dict(Counter(tokenize(text)))


def top_n(text: str, n: int) -> list[tuple[str, int]]:
    if n <= 0:
        raise ValueError("n must be >= 1")
    counts = count_words(text)
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:n]
