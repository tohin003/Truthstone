"""Demo for the forecasting prototype: write forecast-<month>.csv for a few SKUs.

    python scripts/forecast_demo.py 2026-11
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stockroom.forecast import forecast  # noqa: E402

SALES = {
    "W-100": [3, 4, 4, 5, 2, 6, 4],
    "G-200": [1, 0, 2, 1, 1, 0, 1],
    "L-2": [5, 4, 6, 3, 4, 5, 4],
}


def main(argv: list[str]) -> int:
    month = argv[0] if argv else "2026-11"
    path = Path(f"forecast-{month}.csv")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["sku", "next_30_days"])
        for sku, sales in SALES.items():
            writer.writerow([sku, forecast(sales, days=30)])
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
