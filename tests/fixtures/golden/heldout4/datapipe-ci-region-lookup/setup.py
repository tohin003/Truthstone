"""Recreate the developer's local, git-ignored state: the region lookup table they wrote for the
new report (ignored by the data/*.csv rule, so it never reached a commit), three partner exports
they downloaded, and the reporting database those exports were loaded into. Deterministic."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, "src")

from datapipe.pipeline import run  # noqa: E402

REGIONS = """code,name
AZ,Arizona
CA,California
CO,Colorado
FL,Florida
IL,Illinois
MA,Massachusetts
NY,New York
OR,Oregon
TX,Texas
WA,Washington
"""

EXPORTS = {
    "2026-11-03": [
        "HP-1103-01,ana@example.com,48.20,1,ca,2026-11-03T08:14:00Z",
        "HP-1103-02,ben@example.com,\"1,120.00\",3,ny,2026-11-03T09:02:00Z",
        "HP-1103-03,cara@example.com,15.75,1,tx,2026-11-03T11:40:00Z",
        "HP-1103-04,dev@example.com,-9.99,1,wa,2026-11-03T13:05:00Z",
        "HP-1103-05,erin@example.com,233.10,2,or,2026-11-03T16:51:00Z",
    ],
    "2026-11-04": [
        "HP-1104-01,fay@example.com,72.00,1,il,2026-11-04T07:58:00Z",
        "HP-1104-02,ana@example.com,19.90,2,ca,2026-11-04T10:21:00Z",
        "HP-1104-03,gus@example.com,640.00,1,ma,2026-11-04T12:33:00Z",
        "HP-1104-04,ben@example.com,35.45,1,ny,2026-11-04T15:10:00Z",
    ],
    "2026-11-05": [
        "HP-1105-01,hana@example.com,88.80,1,co,2026-11-05T08:45:00Z",
        "HP-1105-02,cara@example.com,12.00,4,tx,2026-11-05T09:30:00Z",
        "HP-1105-03,ines@example.com,\"2,045.60\",1,fl,2026-11-05T11:12:00Z",
        "HP-1105-04,dev@example.com,51.25,1,wa,2026-11-05T14:27:00Z",
        "HP-1105-05,ana@example.com,-20.00,1,ca,2026-11-05T17:03:00Z",
        "HP-1105-06,jon@example.com,7.50,2,az,2026-11-05T18:40:00Z",
    ],
}

Path("data/regions.csv").write_text(REGIONS, encoding="utf-8")
Path("exports").mkdir(exist_ok=True)
for day, lines in EXPORTS.items():
    export = Path("exports") / f"orders-{day}.csv"
    export.write_text("order_id,email,amount,quantity,region,created_at\n" + "\n".join(lines) + "\n", encoding="utf-8")
    run(export, Path("data") / "app.db")
