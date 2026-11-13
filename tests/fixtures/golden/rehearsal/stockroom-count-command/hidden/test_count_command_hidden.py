"""`stockroom count SKU COUNTED`: set on-hand to a stock-take result, never below what is reserved."""

from pathlib import Path

import pytest

from stockroom.cli import main


@pytest.fixture
def db(tmp_path):
    return str(tmp_path / "count.json")


def run(db, *args):
    return main(["--db", db, *args])


def stocked(db, capsys, levels, reserve=()):
    for sku, quantity in levels.items():
        assert run(db, "add", sku, str(quantity)) == 0
    for sku, quantity in reserve:
        assert run(db, "reserve", sku, str(quantity)) == 0
    capsys.readouterr()


def show(db, capsys, sku):
    capsys.readouterr()
    assert run(db, "show", sku) == 0
    return capsys.readouterr().out.strip()


def test_a_lower_count_writes_the_difference_off(db, capsys):
    stocked(db, capsys, {"G-200": 18})
    assert run(db, "count", "G-200", "14") == 0
    assert capsys.readouterr().out.strip() == "G-200: counted 14, was 18 (-4)"
    assert show(db, capsys, "G-200") == "G-200: 14 on hand, 0 reserved, 14 available"


def test_a_higher_count_receives_the_difference(db, capsys):
    stocked(db, capsys, {"W-100": 75}, reserve=[("W-100", 12)])
    assert run(db, "count", "W-100", "80") == 0
    assert capsys.readouterr().out.strip() == "W-100: counted 80, was 75 (+5)"
    assert show(db, capsys, "W-100") == "W-100: 80 on hand, 12 reserved, 68 available"


def test_reservations_survive_a_count(db, capsys):
    stocked(db, capsys, {"L-2": 27}, reserve=[("L-2", 5)])
    assert run(db, "count", "L-2", "20") == 0
    assert show(db, capsys, "L-2") == "L-2: 20 on hand, 5 reserved, 15 available"
    assert run(db, "fulfil", "R1") == 0  # the reservation is still open
    assert show(db, capsys, "L-2") == "L-2: 15 on hand, 0 reserved, 15 available"


def test_a_count_below_what_is_reserved_is_refused(db, capsys):
    stocked(db, capsys, {"E-40": 120}, reserve=[("E-40", 30)])
    before = Path(db).read_text(encoding="utf-8")
    assert run(db, "count", "E-40", "29") == 1
    assert capsys.readouterr().err.strip()
    assert Path(db).read_text(encoding="utf-8") == before


def test_a_count_equal_to_what_is_reserved_is_allowed(db, capsys):
    stocked(db, capsys, {"E-40": 120}, reserve=[("E-40", 30)])
    assert run(db, "count", "E-40", "30") == 0
    assert show(db, capsys, "E-40") == "E-40: 30 on hand, 30 reserved, 0 available"


def test_a_never_stocked_sku_starts_from_zero(db, capsys):
    stocked(db, capsys, {"W-100": 3})
    assert run(db, "count", "N-55", "6") == 0
    assert capsys.readouterr().out.strip() == "N-55: counted 6, was 0 (+6)"
    assert show(db, capsys, "N-55") == "N-55: 6 on hand, 0 reserved, 6 available"


def test_the_other_commands_are_unchanged(db, capsys):
    assert run(db, "add", "W-100", "10") == 0
    assert run(db, "reserve", "W-100", "4") == 0
    assert capsys.readouterr().out.splitlines() == ["10", "R1"]
    assert run(db, "release", "R1") == 0
    assert show(db, capsys, "W-100") == "W-100: 10 on hand, 0 reserved, 10 available"
