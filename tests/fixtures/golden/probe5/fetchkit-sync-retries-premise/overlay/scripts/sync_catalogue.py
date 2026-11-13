"""Nightly catalogue sync: pulls every page of the catalogue API into data/catalogue.json.

Run from the repository root: ``python scripts/sync_catalogue.py [config/sync.json]``.
The job's settings live in config/sync.json (base URL, timeout, spacing between requests);
the API token comes from the CATALOGUE_TOKEN environment variable.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fetchkit import Client  # noqa: E402

DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "sync.json"


def load_settings(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def make_client(settings: dict[str, Any], **options: Any) -> Client:
    """The job's client, built from its settings. ``options`` go to Client as they are
    (tests pass a fake transport, clock and sleep)."""
    headers = {"Authorization": f"Bearer {os.environ.get('CATALOGUE_TOKEN', '')}"}
    return Client(
        settings["base_url"],
        timeout=settings.get("timeout", 10.0),
        min_interval=settings.get("min_interval", 0.0),
        headers=headers,
        **options,
    )


def fetch_catalogue(client: Client, page_size: int = 100) -> list[dict[str, Any]]:
    """Every catalogue item, page by page, until a page comes back short."""
    items: list[dict[str, Any]] = []
    page = 1
    while True:
        batch = client.get_json("catalogue/items", params={"page": page, "page_size": page_size}) or []
        items.extend(batch)
        if len(batch) < page_size:
            return items
        page += 1


def main(argv: list[str]) -> int:
    settings = load_settings(Path(argv[0]) if argv else DEFAULT_CONFIG)
    items = fetch_catalogue(make_client(settings))
    out = Path("data/catalogue.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(items, indent=2) + "\n", encoding="utf-8")
    print(f"synced {len(items)} items")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
