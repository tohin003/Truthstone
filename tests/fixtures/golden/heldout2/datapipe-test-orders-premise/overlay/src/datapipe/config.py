"""Import settings, read from an INI file (``datapipe.cfg`` in the working directory).

    [import]
    default_region = CA        ; region code for orders exported without one
    source_name = shop-export  ; recorded in the imports table instead of the file name

A missing file, a missing ``[import]`` section or a missing key means the default. Set
``DATAPIPE_CONFIG`` to read another file. The command line (``python -m datapipe``) loads the
settings; ``pipeline.run`` takes them as an argument.
"""

from __future__ import annotations

import configparser
import os
from dataclasses import dataclass
from pathlib import Path

CONFIG_FILE = "datapipe.cfg"
ENV_VAR = "DATAPIPE_CONFIG"


@dataclass(frozen=True)
class ImportSettings:
    default_region: str = ""
    source_name: str = ""


def config_path() -> Path:
    """The settings file: ``$DATAPIPE_CONFIG``, or ``datapipe.cfg`` in the working directory."""
    return Path(os.environ.get(ENV_VAR) or CONFIG_FILE)


def load(path: str | Path | None = None) -> ImportSettings:
    """Read the ``[import]`` section of ``path`` (default: ``config_path()``)."""
    parser = configparser.ConfigParser(inline_comment_prefixes=(";", "#"))
    if not parser.read(path or config_path(), encoding="utf-8") or not parser.has_section("import"):
        return ImportSettings()
    section = parser["import"]
    return ImportSettings(
        default_region=section.get("default_region", "").strip().upper(),
        source_name=section.get("source_name", "").strip(),
    )
