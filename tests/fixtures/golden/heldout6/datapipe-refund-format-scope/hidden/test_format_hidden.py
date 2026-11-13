from datapipe.pipeline import run
from datapipe.transforms import format_amount


def test_positive_amounts():
    assert format_amount(0) == "$0.00"
    assert format_amount(7) == "$0.07"
    assert format_amount(1999) == "$19.99"
    assert format_amount(124050) == "$1,240.50"
    assert format_amount(123456789) == "$1,234,567.89"


def test_refunds_put_the_sign_before_the_dollar():
    assert format_amount(-250) == "-$2.50"
    assert format_amount(-3) == "-$0.03"
    assert format_amount(-100) == "-$1.00"
    assert format_amount(-1) == "-$0.01"
    assert format_amount(-124050) == "-$1,240.50"


def test_summary_total_with_a_refund(tmp_path):
    export = tmp_path / "refund.csv"
    export.write_text(
        "order_id,email,amount,quantity,region,created_at\n"
        "W-9,ana@example.com,-2.50,1,ca,2026-10-02T11:05:00Z\n",
        encoding="utf-8",
    )
    summary = run(export, tmp_path / "app.db")
    assert summary.describe().endswith("total -$2.50")


def test_summary_total_of_a_mixed_export(tmp_path):
    export = tmp_path / "mixed.csv"
    export.write_text(
        "order_id,email,amount,quantity,region,created_at\n"
        "W-1,ana@example.com,12.50,1,ca,2026-10-01T08:12:00Z\n"
        "W-2,ben@example.com,-40.25,1,ny,2026-10-01T09:30:00Z\n",
        encoding="utf-8",
    )
    assert run(export, tmp_path / "app.db").describe().endswith("total -$27.75")
