"""Command line entry point: python -m textcli count <path>."""
import argparse
import sys
from pathlib import Path


def count_text(text: str) -> tuple[int, int, int]:
    """Return (lines, words, chars) of text; a last line without newline counts as a line."""
    if not isinstance(text, str):
        raise TypeError("text must be str")
    lines = text.count("\n")
    if text and not text.endswith("\n"):
        lines += 1
    return lines, len(text.split()), len(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="textcli")
    sub = parser.add_subparsers(dest="command", required=True)
    count = sub.add_parser("count", help="count lines, words and characters of a UTF-8 file")
    count.add_argument("path")
    args = parser.parse_args(argv)

    try:
        data = Path(args.path).read_bytes()
    except FileNotFoundError:
        try:
            sys.stderr.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
        print(f"error: file not found: {args.path}", file=sys.stderr)
        return 2
    lines, words, chars = count_text(data.decode("utf-8"))
    print(f"{lines} {words} {chars}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
