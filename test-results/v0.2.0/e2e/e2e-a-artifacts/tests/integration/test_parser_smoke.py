from pathlib import Path

from scorepipe.parser import parse_scores


def test_parser_reads_an_export_file(tmp_path: Path):
    f = tmp_path / "export.csv"
    f.write_text("name,score\nkim,90\nlee,85\n", encoding="utf-8")
    assert [r["name"] for r in parse_scores(f.read_text(encoding="utf-8"))] == ["kim", "lee"]
