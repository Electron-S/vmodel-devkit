"""HTTP API (DESIGN-003): GET /grade?score=N -> JSON; python -m gradecalc.server [--port N]."""
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from gradecalc.grading import grade


def handle(path: str) -> tuple[int, dict]:
    parts = urlsplit(path)
    if parts.path != "/grade":
        return 404, {"error": "없는 경로입니다"}
    values = parse_qs(parts.query).get("score") or []
    if len(values) != 1:
        return 400, {"error": "score 파라미터가 하나 필요합니다"}
    try:
        score = int(values[0].strip())
        return 200, {"score": score, "grade": grade(score)}
    except (ValueError, TypeError):
        return 400, {"error": f"점수는 0에서 100 사이의 정수여야 합니다: {values[0]}"}


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        status, body = handle(self.path)
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    port = int(args[1]) if len(args) == 2 and args[0] == "--port" else 0
    server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    print(f"PORT {server.server_address[1]}", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
