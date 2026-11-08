"""Export timestamps with a numeric UTC offset are read and converted to UTC; Z still works."""

from datetime import datetime, timezone

import pytest

from datapipe.db import connect, daily_totals
from datapipe.pipeline import run
from datapipe.readers import ReadError, parse_timestamp, read_csv

UTC = timezone.utc


@pytest.mark.parametrize(
    "text, expected",
    [
        ("2026-11-05T09:30:00+01:00", datetime(2026, 11, 5, 8, 30, tzinfo=UTC)),
        ("2026-11-05T09:30:00+00:00", datetime(2026, 11, 5, 9, 30, tzinfo=UTC)),
        ("2026-11-05T09:30:00-05:00", datetime(2026, 11, 5, 14, 30, tzinfo=UTC)),
        ("2026-11-05T00:30:00+02:00", datetime(2026, 11, 4, 22, 30, tzinfo=UTC)),
        ("2026-11-05T09:30:00Z", datetime(2026, 11, 5, 9, 30, tzinfo=UTC)),
    ],
)
def test_offsets_are_converted_to_utc(text, expected):
    moment = parse_timestamp(text)
    assert moment == expected
    assert moment.utcoffset().total_seconds() == 0


def test_garbage_is_still_rejected():
    with pytest.raises(ValueError):
        parse_timestamp("yesterday")


def test_an_export_with_offsets_reads_and_loads_by_utc_day(tmp_path):
    export = tmp_path / "partner.csv"
    export.write_text(
        "order_id,email,amount,created_at\n"
        "NP-1,a@example.com,10.00,2026-11-05T00:30:00+01:00\n"
        "NP-2,b@example.com,5.00,2026-11-05T12:00:00+00:00\n"
        "NP-3,c@example.com,2.50,2026-11-05T08:00:00Z\n",
        encoding="utf-8",
    )
    rows = read_csv(export)
    assert [row["created_at"] for row in rows] == [
        datetime(2026, 11, 4, 23, 30, tzinfo=UTC),
        datetime(2026, 11, 5, 12, 0, tzinfo=UTC),
        datetime(2026, 11, 5, 8, 0, tzinfo=UTC),
    ]
    run(export, tmp_path / "app.db")
    conn = connect(tmp_path / "app.db")
    assert daily_totals(conn) == {"2026-11-04": 1000, "2026-11-05": 750}
    conn.close()


def test_a_bad_timestamp_names_the_line(tmp_path):
    export = tmp_path / "partner.csv"
    export.write_text(
        "order_id,email,amount,created_at\n"
        "NP-1,a@example.com,10.00,2026-11-05T09:30:00+01:00\n"
        "NP-2,b@example.com,5.00,5 Nov 2026\n",
        encoding="utf-8",
    )
    with pytest.raises(ReadError, match="line 3"):
        read_csv(export)
