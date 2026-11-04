"""textkit: small text utilities shared by the docs site and the export jobs.

Import from the modules directly (``from textkit.slug import slugify``). The 0.x case
helpers are still reachable as attributes of the package for old callers.
"""

__version__ = "1.4.0"

_LEGACY_NAMES = frozenset({"camelize", "dasherize", "humanize", "underscore"})


def __getattr__(name: str):
    # textkit 0.x exposed its case helpers at the top level (``textkit.camelize``).
    if name in _LEGACY_NAMES:
        from textkit import legacy_case

        return getattr(legacy_case, name)
    raise AttributeError(f"module 'textkit' has no attribute {name!r}")
