"""The nightly export job: the day's invoices (JSON) in, the CSV that accounting imports out.

Run by cron on the billing host, from the repository root:

    PYTHONPATH=src python deploy/nightly_export.py invoices.json export.csv

Logging is configured from deploy/logging.ini. The job's stderr is mailed to billing every
morning, so that file decides what billing gets to see.
"""

from __future__ import annotations

import json
import logging
import logging.config
import sys
from decimal import Decimal
from pathlib import Path

from ledger.discounts import parse_code
from ledger.export import to_csv
from ledger.invoice import Invoice, LineItem

LOGGING_CONFIG = Path(__file__).with_name("logging.ini")


def load_invoices(path: Path) -> list[Invoice]:
    """Invoices from the billing service's JSON dump (amounts as strings)."""
    records = json.loads(path.read_text(encoding="utf-8"))
    return [
        Invoice(
            record["number"],
            record["customer"],
            record["region"],
            [
                LineItem(item["sku"], item["description"], int(item["quantity"]), Decimal(item["unit_price"]))
                for item in record["items"]
            ],
            [parse_code(code) for code in record.get("discounts", [])],
        )
        for record in records
    ]


def main(argv: list[str]) -> int:
    logging.config.fileConfig(LOGGING_CONFIG, disable_existing_loggers=False)
    log = logging.getLogger("billing.nightly")
    if len(argv) != 2:
        print("usage: nightly_export.py <invoices.json> <export.csv>", file=sys.stderr)
        return 2
    source, target = Path(argv[0]), Path(argv[1])
    invoices = load_invoices(source)
    target.write_text(to_csv(invoices), encoding="utf-8")
    log.info("exported %d invoices to %s", len(invoices), target)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
