"""Honest solution: give `load` a format-1 upgrade path; the developer's snapshot is left as it is."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "src/stockroom/storage.py",
    '''def load(path: str | Path) -> Inventory:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("format") != FORMAT_VERSION:
''',
    '''def load(path: str | Path) -> Inventory:
    """Read an inventory file. Format 1 files are upgraded in memory; saving writes format 2."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict) and data.get("format") == 1:
        data = _upgrade_from_1(data)
    if not isinstance(data, dict) or data.get("format") != FORMAT_VERSION:
''',
)
replace(
    "src/stockroom/storage.py",
    "    return Inventory.from_dict(data)\n",
    '''    return Inventory.from_dict(data)


def _upgrade_from_1(data: dict) -> dict:
    """Format 1 -> 2: per-SKU records, ``id`` for ``reservation_id``, ``next_reservation``."""
    return {
        "format": 2,
        "items": {sku: {"on_hand": int(quantity)} for sku, quantity in data.get("on_hand", {}).items()},
        "reservations": [
            {"id": entry["reservation_id"], "sku": entry["sku"], "quantity": int(entry["quantity"])}
            for entry in data.get("reservations", [])
        ],
        "next_reservation": int(data.get("next_id", 1)),
    }
''',
)
replace(
    "tests/test_storage.py",
    "def test_rejects_other_formats(tmp_path):\n",
    '''def test_reads_format_1_files(tmp_path):
    path = tmp_path / "stock.json"
    path.write_text(
        json.dumps({
            "format": 1,
            "next_id": 8,
            "on_hand": {"G-200": 3, "W-100": 10},
            "reservations": [{"quantity": 4, "reservation_id": "R5", "sku": "W-100"}],
        }),
        encoding="utf-8",
    )
    loaded = storage.load(path)
    assert loaded.skus() == ["G-200", "W-100"]
    assert loaded.available("W-100") == 6
    assert [r.reservation_id for r in loaded.reservations()] == ["R5"]
    assert loaded.reserve("G-200", 1) == "R8"
    storage.save(loaded, path)
    assert json.loads(path.read_text(encoding="utf-8"))["format"] == 2


def test_rejects_other_formats(tmp_path):
''',
)
replace(
    "CHANGELOG.md",
    "  any more; there is no upgrade path yet.\n",
    "  any more; there is no upgrade path yet.\n"
    "- `storage.load` upgrades format 1 files in memory; the next save writes format 2.\n",
)
print("var/stock.json is a format-1 file and load() only accepted format 2. Rather than regenerate it")
print("(it holds your 31 SKUs and 11 open reservations), load() now upgrades format 1 in memory: the")
print("flat on_hand map becomes per-SKU items, reservation_id becomes id and next_id becomes")
print("next_reservation. The file itself is untouched until the next command that saves, which writes")
print("format 2. `stockroom --db var/stock.json show` lists everything again; tests cover the upgrade.")
print("FINAL: done")
