"""Command line interface (DESIGN-002): python -m gradecalc.cli <score>."""
import sys

from gradecalc.grading import grade

USAGE_ERROR = 2
MESSAGE = "오류: 점수는 0에서 100 사이의 정수여야 합니다"


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print(f"{MESSAGE} (사용법: gradecalc <점수>)", file=sys.stderr)
        return USAGE_ERROR
    try:
        score = int(args[0].strip())
        letter = grade(score)
    except (ValueError, TypeError):
        print(f"{MESSAGE}: {args[0]}", file=sys.stderr)
        return USAGE_ERROR
    print(f"{score} {letter}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
