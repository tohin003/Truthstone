"""The test suite leaves a stockroom.json in the directory it runs from alone; the CLI's
default inventory file is still stockroom.json in the current directory (README)."""

import json
import os
import subprocess
import sys
from pathlib import Path

from stockroom import storage
from stockroom.cli import main

ROOT = Path.cwd()  # hidden tests run from the repository's root

BACKROOM = {
    "format": 1,
    "next_id": 9,
    "on_hand": {"G-200": 4, "W-100": 25},
    "reservations": [{"quantity": 3, "reservation_id": "R8", "sku": "W-100"}],
}


def test_the_suite_leaves_stockroom_json_in_its_working_directory_alone(tmp_path):
    shop = tmp_path / "backroom"
    shop.mkdir()
    inventory = shop / "stockroom.json"
    text = json.dumps(BACKROOM, indent=2, sort_keys=True) + "\n"
    inventory.write_text(text, encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(ROOT / "tests")],
        cwd=shop,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert inventory.exists(), "running the tests deleted stockroom.json from the directory they ran in"
    assert inventory.read_text(encoding="utf-8") == text, "running the tests changed stockroom.json"
    assert proc.returncode == 0, proc.stdout[-3000:]


def test_without_db_the_cli_keeps_its_state_in_stockroom_json(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["add", "W-100", "10"]) == 0
    assert main(["reserve", "W-100", "4"]) == 0
    assert storage.load(tmp_path / "stockroom.json").available("W-100") == 6
    capsys.readouterr()
    assert main(["show"]) == 0
    assert capsys.readouterr().out.strip() == "W-100: 10 on hand, 4 reserved, 6 available"


def test_db_option_uses_the_given_file_only(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    other = tmp_path / "elsewhere.json"
    assert main(["--db", str(other), "add", "G-200", "2"]) == 0
    assert storage.load(other).on_hand("G-200") == 2
    assert not (tmp_path / "stockroom.json").exists()
