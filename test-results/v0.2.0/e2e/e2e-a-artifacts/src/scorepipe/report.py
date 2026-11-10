"""Score summary report command line: python -m scorepipe.report <file> (summarize is re-exported)."""
import json
import sys

from scorepipe.summary import summarize

__all__ = ["main", "summarize"]
USAGE = "usage: python -m scorepipe.report <file>"


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print(USAGE, file=sys.stderr)
        return 2
    path = args[0]
    try:
        with open(path, encoding="utf-8-sig") as f:
            text = f.read()
    except (OSError, UnicodeDecodeError) as exc:
        print(f"error: cannot read {path}: {exc}", file=sys.stderr)
        return 2
    try:
        result = summarize(text)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
