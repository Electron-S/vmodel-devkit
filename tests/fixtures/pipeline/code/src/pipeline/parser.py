"""Score record parser (DESIGN-001, provider of IF-001)."""


def parse(text: str) -> list[dict]:
    if not isinstance(text, str):
        raise TypeError("text must be str")
    records = []
    for no, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        name, sep, score = line.partition(",")
        if not sep or not name.strip():
            raise ValueError(f"line {no}: expected 'name,score'")
        try:
            value = int(score)
        except ValueError:
            raise ValueError(f"line {no}: score must be an integer") from None
        records.append({"name": name.strip(), "score": value})
    return records
