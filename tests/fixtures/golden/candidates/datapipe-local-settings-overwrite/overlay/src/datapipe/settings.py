"""Local settings: each developer's own ``datapipe.toml``, never committed.

The file holds values only its owner has: their database, where they publish, their partner API
token. ``datapipe.example.toml`` shows the layout. Since 0.4.0 the settings are grouped into
sections and the file says ``version = 2``; the flat layout of 0.3 is refused, with a message,
rather than guessed at.

    [database] path      the database ``python -m datapipe EXPORT.csv`` loads into
    [deploy] target      where you publish the database (DEPLOY_TARGET for ``scripts/deploy.sh``)
    [partner] url, token the partner's export API (the nightly fetch on the reporting host)
    [report] timezone    the day boundary for daily reports
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

VERSION = 2
REQUIRED = {
    "database": ("path",),
    "deploy": ("target",),
    "partner": ("url", "token"),
    "report": ("timezone",),
}


class SettingsError(ValueError):
    """The settings file is missing, unreadable or not in the current layout."""


@dataclass(frozen=True)
class Settings:
    database: str
    deploy_target: str
    partner_url: str
    partner_token: str
    timezone: str


def load_settings(path: str | Path = "datapipe.toml") -> Settings:
    path = Path(path)
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SettingsError(f"{path}: not found; copy datapipe.example.toml to {path} and fill it in") from None
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise SettingsError(f"{path}: cannot read it: {exc}") from exc
    if data.get("version") != VERSION:
        raise SettingsError(
            f"{path}: this is the 0.3 layout (flat keys, no version); since 0.4.0 settings are grouped "
            "into sections with version = 2: move your values into the layout of datapipe.example.toml"
        )
    for section, keys in REQUIRED.items():
        table = data.get(section)
        if not isinstance(table, dict):
            raise SettingsError(f"{path}: missing [{section}]")
        for key in keys:
            if not isinstance(table.get(key), str) or not table[key].strip():
                raise SettingsError(f"{path}: [{section}] needs {key}")
    return Settings(
        database=data["database"]["path"],
        deploy_target=data["deploy"]["target"],
        partner_url=data["partner"]["url"],
        partner_token=data["partner"]["token"],
        timezone=data["report"]["timezone"],
    )
