import json
from pathlib import Path

from textkit import exports

REPO = Path(__file__).resolve().parents[1]


def config(tmp_path, jobs):
    path = tmp_path / "exports.json"
    path.write_text(json.dumps({"jobs": jobs}), encoding="utf-8")
    return path


def test_the_shipped_config_lists_the_jobs():
    names = [job["name"] for job in exports.load_jobs(REPO / "config" / "exports.json")]
    assert names == ["orders-csv", "stock-report-md", "partner-feed-json"]


def test_header_labels_use_the_configured_function(tmp_path):
    [job] = exports.load_jobs(config(tmp_path, [{"name": "j", "formatter": "textkit.formats.csv_fmt",
                                               "labels": "textkit.case.to_kebab", "columns": ["created_at"]}]))
    assert exports.header_labels(job) == ["created-at"]


def test_render(tmp_path):
    [job] = exports.load_jobs(config(tmp_path, [{"name": "j", "formatter": "textkit.formats.csv_fmt",
                                               "labels": "textkit.case.to_snake", "columns": ["orderId", "qty"]}]))
    assert exports.render(job, [["W-1", 3]]).splitlines() == ["order_id,qty", "W-1,3"]
