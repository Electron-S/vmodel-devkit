"""Tokenizer (DESIGN-001)."""
import re

_WORD = re.compile(r"\w+")


def tokenize(text: str) -> list[str]:
    if not isinstance(text, str):
        raise TypeError("text must be str")
    return [m.group(0).lower() for m in _WORD.finditer(text)]
