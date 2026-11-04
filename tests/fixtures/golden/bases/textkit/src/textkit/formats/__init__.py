"""Table renderers.

Each module exposes ``render(rows, headers) -> str``: ``headers`` is a sequence of column
names and every row a sequence of values in the same order. ``None`` renders as an
empty cell; any other value goes through ``str``. Import the module you need, e.g.
``from textkit.formats.csv_fmt import render``.
"""
