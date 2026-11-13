import pytest

from stockroom.cli import main

NEW_HELP = "write stock off (at most what is available; reserved stock cannot be written off)"


def test_top_level_help_shows_the_new_remove_text(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["--help"])
    assert exit_info.value.code == 0
    out = " ".join(capsys.readouterr().out.split())
    assert NEW_HELP in out
    assert "receive stock" in out


def test_remove_still_writes_stock_off(tmp_path, capsys):
    db = str(tmp_path / "stock.json")
    assert main(["--db", db, "add", "W-100", "10"]) == 0
    assert main(["--db", db, "reserve", "W-100", "4"]) == 0
    assert main(["--db", db, "remove", "W-100", "6"]) == 0
    assert main(["--db", db, "remove", "W-100", "1"]) == 1
    capsys.readouterr()
    assert main(["--db", db, "show", "W-100"]) == 0
    assert capsys.readouterr().out.strip() == "W-100: 4 on hand, 4 reserved, 0 available"
