"""Score export parser (existing component, owned by the grading team).

parse_scores(text) -> list[dict]
    One {"name": str, "score": str} per data line, in input order. Scores are returned as the original text (for
    example "07" or "100") because the export format allows zero padding; callers convert them as they need.
    A first line equal to "name,score" is a header and is skipped. Blank lines are ignored.
    A malformed line raises ValueError("line N: <reason>"), N counted from 1 over all lines of the input
    (header and blank lines included).
"""


def parse_scores(text: str) -> list[dict]:
    if not isinstance(text, str):
        raise TypeError("text must be str")
    records = []
    for no, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or (no == 1 and line.replace(" ", "") == "name,score"):
            continue
        name, sep, score = line.partition(",")
        name, score = name.strip(), score.strip()
        if not sep or not name:
            raise ValueError(f"line {no}: expected 'name,score'")
        if not score.isdigit():
            raise ValueError(f"line {no}: score must be digits")
        records.append({"name": name, "score": score})
    return records
