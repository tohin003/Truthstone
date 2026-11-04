"""The product's names, current and former, and the compatibility rules built on them.

A product rename (``scripts/rename_product.py``; see ``docs/RENAME.md``) rewrites the
current name everywhere like any other text, then records the old name in ``FORMER``.
Everything that must keep working for an install made under an old name asks this module,
so that one entry is the whole compatibility layer:

* **Environment variables** (:func:`env`). ``TRUTHSTONE_HOME`` wins; the same setting under
  a former name is the fallback. The first non-empty value counts.
* **The data directory** (:func:`data_dir`, :func:`migrated`). ``~/.truthstone``, unless
  it does not exist and a former name's directory does: then that one, until the move
  ``truthstone doctor`` suggests (:func:`migration_notes`). Files named after the product
  inside it, such as the database, follow the same rule.
* **Ownership markers** (:func:`variants`). The installers recognise hook entries written
  under a former name, so reinstalling replaces them and uninstalling removes them.

Shell scripts cannot import this, so the generated Codex launcher carries the same
environment fallbacks as plain shell lines (:func:`shell_fallbacks`).

Stdlib-only and cheap to import: the hook forwarders import it on every call.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

# The current name in its three spellings: prose, identifiers and paths, environment.
DISPLAY = "Truthstone"
SLUG = "truthstone"
UPPER = "TRUTHSTONE"

# Former names, newest first, as (display, slug, upper). scripts/rename_product.py adds the
# old name here when it renames the product; nothing else in the code spells one out.
# rename-tool: keep-begin former-names
FORMER: tuple[tuple[str, str, str], ...] = (("AgentGuard", "agentguard", "AGENTGUARD"),)
# rename-tool: keep-end


def _translate(text: str, source: tuple[str, str, str], target: tuple[str, str, str]) -> str:
    """Respell every spelling of `source` in `text` as the same spelling of `target`.

    One left-to-right pass, longest spelling first, so nothing it writes is rewritten again.
    """
    pairs = sorted(((s, t) for s, t in zip(source, target, strict=True) if s), key=lambda p: -len(p[0]))
    out: list[str] = []
    i = 0
    while i < len(text):
        for old, new in pairs:
            if text.startswith(old, i):
                out.append(new)
                i += len(old)
                break
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def as_former(text: str, former: tuple[str, str, str]) -> str:
    """`text`, written with the current name, as it was written under `former`."""
    return _translate(text, (DISPLAY, SLUG, UPPER), former)


def variants(text: str) -> list[str]:
    """`text` as written now, then as each former name would have written it.

    ``variants("X-Truthstone")`` lists every ownership header an install of any version may
    have written. Without former names it is just ``[text]``.
    """
    out = [text]
    for former in FORMER:
        alternative = as_former(text, former)
        if alternative not in out:
            out.append(alternative)
    return out


def written_under_former_name(text: str, *markers: str) -> bool:
    """Whether `text` contains one of `markers` as a former name spelled it."""
    return any(variant in text for marker in markers for variant in variants(marker)[1:])


def env(name: str, environ: Mapping[str, str] | None = None) -> str | None:
    """The value of environment variable `name`, falling back to its former-name versions.

    ``env("TRUTHSTONE_HOME")`` reads ``TRUTHSTONE_HOME`` and, after a rename, the same
    variable under each former name. The first non-empty value wins, the current name
    first, so an old setting keeps working without ever overriding a new one.
    """
    source = os.environ if environ is None else environ
    for candidate in variants(name):
        value = source.get(candidate)
        if value:
            return str(value)
    return None


def env_flag(name: str, environ: Mapping[str, str] | None = None) -> bool:
    """A boolean switch such as ``TRUTHSTONE_DISABLE``: 1, true, yes or on."""
    return (env(name, environ) or "").strip().lower() in {"1", "true", "yes", "on"}


def migrated(path: str) -> str:
    """`path`, or a former name's version of it while only that one exists.

    For things named after the product, such as ``~/.truthstone`` and the database file:
    an install made under a former name keeps finding its data until it is moved.
    """
    if not FORMER or os.path.lexists(path):
        return path
    head, tail = os.path.split(path)
    for alternative in variants(tail)[1:]:
        candidate = os.path.join(head, alternative)
        if os.path.lexists(candidate):
            return candidate
    return path


def default_data_dir() -> str:
    return os.path.join(os.path.expanduser("~"), ".truthstone")


def data_dir() -> str:
    """Where state lives: ``$TRUTHSTONE_HOME`` (or a former name's), else ``~/.truthstone``."""
    explicit = env("TRUTHSTONE_HOME")
    if explicit:
        return os.path.expanduser(explicit)
    return migrated(default_data_dir())


def migration_notes(environ: Mapping[str, str] | None = None) -> list[str]:
    """What ``doctor`` should say about data or settings still under a former name."""
    source = os.environ if environ is None else environ
    notes: list[str] = []
    if not env("TRUTHSTONE_HOME", source):
        current = default_data_dir()
        in_use = migrated(current)
        if in_use != current:
            notes.append(
                f"data is in {in_use}, the former name's directory; it is still used. To move "
                f"it: truthstone daemon stop && mv {in_use} {current}"
            )
    for former in FORMER:
        prefix = former[2] + "_"
        for name in sorted(k for k in source if k.startswith(prefix) and source[k]):
            current_name = UPPER + "_" + name[len(prefix) :]
            if not source.get(current_name):
                notes.append(f"{name} is set: it still works; its current name is {current_name}")
    return notes


def shell_fallbacks(script: str) -> str:
    """POSIX lines that let a shell script's ``$TRUTHSTONE_*`` settings come from a former name.

    For every current-name variable the script reads, one line per former name, newest first:
    ``[ -n "${NEW:-}" ] || [ -z "${OLD+x}" ] || NEW=$OLD``. As in :func:`env`, a non-empty
    current setting wins; and an unset former one leaves the current one unset, so a test
    such as ``${NEW+set}`` keeps its meaning. The script itself reads only current names.
    Empty without former names. ``scripts/rename_product.py`` writes the same lines into
    hand-written scripts.
    """
    if not FORMER:
        return ""
    import re

    keys = sorted(set(re.findall(r"\$\{?" + UPPER + r"_([A-Z0-9_]+)", script)))
    if not keys:
        return ""
    # The markers keep a later rename from rewriting these lines (spelled in two parts here
    # so that this source line itself is not one).
    marker = "# rename-tool" + ": keep"
    lines = [f"{marker}-begin former-settings (settings under a former product name still apply)"]
    for key in keys:
        current = f"{UPPER}_{key}"
        for former in FORMER:
            old = f"{former[2]}_{key}"
            lines.append(f'[ -n "${{{current}:-}}" ] || [ -z "${{{old}+x}}" ] || {current}=${old}')
    lines.append(f"{marker}-end")
    return "\n".join(lines) + "\n\n"
