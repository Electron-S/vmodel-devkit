from gradecalc.cli import main


def test_TEST_004_cli_prints_grade(capsys):
    assert main(["95"]) == 0
    assert capsys.readouterr().out.strip() == "95 A"


def test_TEST_005_cli_rejects_input(capsys):
    assert main(["abc"]) == 2
    assert "오류" in capsys.readouterr().err
    assert main([]) == 2


def test_TEST_006_cli_boundaries(capsys):
    assert main(["100"]) == 0
    assert main(["0"]) == 0
    assert capsys.readouterr().out.split() == ["100", "A", "0", "F"]
