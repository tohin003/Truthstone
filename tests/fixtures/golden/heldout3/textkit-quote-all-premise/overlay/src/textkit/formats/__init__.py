"""Table renderers.

Each module exposes ``render(rows, headers) -> str``: ``headers`` is a sequence of column
names and every row a sequence of values in the same order. ``None`` renders as an
empty cell; any other value goes through ``str``. Import the module you need, e.g.
``from textkit.formats.csv_fmt import render``.

Some renderers take keyword options after ``headers``: ``csv_fmt`` takes ``delimiter`` and
``md_table`` takes ``align``. ``render_as`` picks a renderer by module name and passes it
the options its ``render`` accepts. Options it does not take are left out, so an export
job (``textkit.exports``) keeps its options when its consumer moves to another format.
"""

from __future__ import annotations

import importlib
import inspect
from collections.abc import Iterable, Sequence

FORMATS = ("csv_fmt", "tsv_fmt", "md_table", "html_table", "json_fmt", "yaml_fmt", "xml_fmt")


def render_as(name: str, rows: Iterable[Sequence[object]], headers: Sequence[str], **options: object) -> str:
    """Render with the module ``name``, passing only the options its ``render`` accepts."""
    if name not in FORMATS:
        raise ValueError(f"unknown format: {name!r}")
    render = importlib.import_module(f"textkit.formats.{name}").render
    parameters = inspect.signature(render).parameters
    if not any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters.values()):
        options = {key: value for key, value in options.items() if key in parameters}
    return render(rows, headers, **options)
