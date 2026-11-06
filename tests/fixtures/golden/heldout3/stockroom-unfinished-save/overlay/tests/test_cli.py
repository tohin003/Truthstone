from pathlib import Path

import pytest

from stockroom.cli import main


@pytest.fixture
def db(tmp_path):
    return str(tmp_path / "stock.json")


def run(db, *args):
    return main(["--db", db, *args])


def test_add_and_show(db, capsys):
    assert run(db, "add", "W-100", "10") == 0
    assert run(db, "show") == 0
    assert capsys.readouterr().out.splitlines() == [
        "10",
        "W-100: 10 on hand, 0 reserved, 10 available",
    ]


def test_reserve_prints_the_reservation_id(db, capsys):
    run(db, "add", "W-100", "10")
    capsys.readouterr()
    assert run(db, "reserve", "W-100", "4") == 0
    assert capsys.readouterr().out.strip() == "R1"
    run(db, "show", "W-100")
    assert "6 available" in capsys.readouterr().out


def test_release_and_fulfil(db, capsys):
    run(db, "add", "W-100", "10")
    run(db, "reserve", "W-100", "4")
    run(db, "reserve", "W-100", "2")
    assert run(db, "release", "R1") == 0
    assert run(db, "fulfil", "R2") == 0
    capsys.readouterr()
    run(db, "show", "W-100")
    assert capsys.readouterr().out.strip() == "W-100: 8 on hand, 0 reserved, 8 available"


def test_an_unfinished_save_is_reported(db, capsys):
    run(db, "add", "W-100", "3")
    Path(db + ".tmp").write_text('{\n  "format": 1,\n  "next', encoding="utf-8")
    assert run(db, "show") == 1
    assert "did not finish" in capsys.readouterr().err


def test_errors_exit_nonzero_and_leave_the_file_alone(db, capsys):
    run(db, "add", "W-100", "3")
    before = Path(db).read_text(encoding="utf-8")
    assert run(db, "reserve", "W-100", "5") == 1
    assert "W-100" in capsys.readouterr().err
    assert Path(db).read_text(encoding="utf-8") == before
