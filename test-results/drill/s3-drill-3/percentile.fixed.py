"""점수 목록의 백분위수 계산."""


def percentile(scores: list[int | float], p: int) -> int | float:
    """점수 목록에서 p 백분위수 값을 돌려준다.

    p는 1 이상 100 이하의 정수여야 하며, 점수 목록은 비어 있으면 안 된다.
    조건을 어기면 ValueError를 낸다. 입력 목록은 바꾸지 않는다.
    """
    if isinstance(p, bool) or not isinstance(p, int):
        raise ValueError("p must be an integer between 1 and 100")
    if p < 1 or p > 100:
        raise ValueError("p must be an integer between 1 and 100")

    ordered = sorted(scores)
    count = len(ordered)
    if count == 0:
        raise ValueError("scores must not be empty")

    # nearest-rank: 순위 r = ceil(p*N/100)을 정수 연산으로 구하고 0-기반 인덱스는 r-1
    rank = -(-p * count // 100)
    return ordered[rank - 1]
