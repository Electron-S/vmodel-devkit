"""Find the longest word in a text."""


def longest_word(text: str) -> str:
    """Return the longest whitespace-separated word (first one on ties).

    Raises ValueError if the text contains no words.
    """
    words = text.split()
    if not words:
        raise ValueError("text contains no words")
    return max(words, key=len)
