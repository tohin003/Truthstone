"""Load order exports (CSV) into a SQLite database.

The steps are small and usable on their own: ``readers`` parses an export, ``transforms``
cleans the rows, ``db`` stores and queries them, and ``pipeline.run`` ties them together.
"""

__version__ = "0.3.1"
