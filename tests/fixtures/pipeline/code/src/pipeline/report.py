"""Score summary report (DESIGN-002, DESIGN-003): consumer of IF-001, provider of IF-002."""
import json
import sys

from pipeline.parser import parse


def summarize(text: str) -> dict:
    records = parse(text)
    if not records:
        return {"count": 0, "total": 0, "top": None}
    top = max(records, key=lambda r: (r["score"], r["name"]))
    return {"count": len(records), "total": sum(r["score"] for r in records), "top": top["name"]}


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args:
        with open(args[0], encoding="utf-8") as fh:
            text = fh.read()
    else:
        text = sys.stdin.read()
    print(json.dumps(summarize(text), ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
