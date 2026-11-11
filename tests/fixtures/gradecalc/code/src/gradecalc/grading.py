"""Score to letter grade (DESIGN-001)."""


def grade(score: int) -> str:
    if isinstance(score, bool) or not isinstance(score, int):
        raise TypeError("score must be an int")
    if score < 0 or score > 100:
        raise ValueError("score must be between 0 and 100")
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    return "F"
