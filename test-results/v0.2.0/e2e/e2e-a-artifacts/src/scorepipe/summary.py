"""Score summary computation (provider of the summarize interface)."""
from scorepipe.parser import parse_scores


def summarize(text: str, parser=parse_scores) -> dict:
    records = parser(text)
    if not records:
        return {"count": 0, "total": 0, "average": 0.0, "top": None}
    scores = [int(r["score"]) for r in records]
    count = len(scores)
    total = sum(scores)
    # integer half-up rounding to one decimal place: floor(total*10/count + 0.5)
    average = (total * 20 + count) // (2 * count) / 10
    top = records[scores.index(max(scores))]["name"]
    return {"count": count, "total": total, "average": average, "top": top}
