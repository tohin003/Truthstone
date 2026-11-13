from pathlib import Path

import pytest

from stockroom.csv_import import CountFileError, load_counts

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "count-example.csv"


def test_load_counts_reads_the_sample():
    inventory = load_counts(SAMPLE)
    assert inventory.skus() == ["D-1", "L-2", "W-100"]
    assert inventory.on_hand("W-100") == 12


def test_zero_counts_are_left_out(tmp_path):
    path = tmp_path / "count.csv"
    path.write_text("sku,counted\nW-100,0\nG-200,3\n", encoding="utf-8")
    assert load_counts(path).skus() == ["G-200"]


def test_bad_header(tmp_path):
    path = tmp_path / "count.csv"
    path.write_text("item,qty\nW-100,1\n", encoding="utf-8")
    with pytest.raises(CountFileError):
        load_counts(path)
