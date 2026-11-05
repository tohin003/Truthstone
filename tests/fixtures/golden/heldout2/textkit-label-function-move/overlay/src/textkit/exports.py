"""Export jobs, as configured in ``config/exports.json``.

Each job names its formatter module and the function that turns column names into header
labels, both as dotted paths imported when the job runs::

    {"jobs": [{"name": "orders-csv", "formatter": "textkit.formats.csv_fmt",
               "labels": "textkit.legacy_case.humanize", "columns": ["order_id", "created_at"]}]}
"""

from __future__ import annotations

import importlib
import json
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any

CONFIG = Path("config/exports.json")


def load_jobs(path: str | Path = CONFIG) -> list[dict[str, Any]]:
    return json.loads(Path(path).read_text(encoding="utf-8"))["jobs"]


def resolve(dotted: str) -> Callable[..., Any]:
    """``"package.module.function"`` -> the function."""
    module_name, _, attribute = dotted.rpartition(".")
    return getattr(importlib.import_module(module_name), attribute)


def header_labels(job: dict[str, Any]) -> list[str]:
    label = resolve(job["labels"])
    return [label(column) for column in job["columns"]]


def render(job: dict[str, Any], rows: Iterable[Sequence[object]]) -> str:
    formatter = importlib.import_module(job["formatter"])
    return formatter.render(rows, header_labels(job))
