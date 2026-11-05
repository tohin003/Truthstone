"""Hidden checks: to_label lives in textkit.case, humanize is gone from legacy_case, and every
caller (the CLI's two commands and the shipped export config) still produces labels."""

from pathlib import Path

from textkit import exports, legacy_case
from textkit.case import to_label
from textkit.cli import main

REPO = Path(__file__).resolve().parents[2]


def test_to_label():
    assert to_label("created_at") == "Created at"
    assert to_label("  user__ID ") == "User id"
    assert to_label("") == ""


def test_humanize_left_legacy_case():
    assert not hasattr(legacy_case, "humanize")
    assert legacy_case.underscore("createdAt") == "created_at"


def test_cli_labels_and_human_style(capsys):
    assert main(["labels", "created_at", "updated_by"]) == 0
    assert main(["case", "--style", "human", "ship_to_region"]) == 0
    assert capsys.readouterr().out == "Created at\nUpdated by\nShip to region\n"


def test_the_shipped_export_jobs_still_label_their_columns():
    jobs = {job["name"]: job for job in exports.load_jobs(REPO / "config" / "exports.json")}
    assert exports.header_labels(jobs["orders-csv"]) == ["Order id", "Created at", "Total cents", "Ship to region"]
    assert exports.header_labels(jobs["stock-report-md"]) == ["Sku", "On hand", "Reorder point"]
    assert exports.header_labels(jobs["partner-feed-json"]) == ["sku", "unitPrice", "stockLevel"]
    assert exports.render(jobs["orders-csv"], [["W-1", "2026-10-01", 1250, "CA"]]).startswith("Order id,")
