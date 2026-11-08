import pytest

from stockroom import locking, storage
from stockroom.cli import main


def test_acquire_creates_the_lock_and_a_second_acquire_is_refused(tmp_path):
    inventory = tmp_path / "stock.json"
    lock = locking.acquire(inventory)
    assert lock == tmp_path / "stock.json.lock"
    assert lock.read_text(encoding="utf-8").startswith("pid ")
    with pytest.raises(locking.LockedError, match="locked by another stockroom process"):
        locking.acquire(inventory)
    locking.release(lock)
    assert not lock.exists()


def test_commands_release_the_lock_when_they_finish(tmp_path):
    db = tmp_path / "stock.json"
    assert main(["--db", str(db), "add", "W-100", "5"]) == 0
    assert main(["--db", str(db), "reserve", "W-100", "9"]) == 1  # a failed command too
    assert not (tmp_path / "stock.json.lock").exists()


def test_a_locked_inventory_is_left_alone(tmp_path, capsys):
    db = tmp_path / "stock.json"
    main(["--db", str(db), "add", "W-100", "5"])
    before = db.read_text(encoding="utf-8")
    (tmp_path / "stock.json.lock").write_text("pid 4242, since 2026-11-01T09:00:00Z\n", encoding="utf-8")
    assert main(["--db", str(db), "add", "W-100", "1"]) == 1
    assert "locked by another stockroom process (pid 4242" in capsys.readouterr().err
    assert db.read_text(encoding="utf-8") == before
    assert storage.load(db).on_hand("W-100") == 5
