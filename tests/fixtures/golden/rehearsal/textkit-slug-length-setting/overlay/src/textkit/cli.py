"""The ``textkit`` command.

    textkit case --style kebab "Hello World"     -> hello-world
    textkit slug "Crème Brûlée"                  -> creme-brulee
    textkit labels created_at updated_by         -> Created at / Updated by

Defaults come from the ``[textkit]`` section of ``textkit.ini`` in the directory the
command runs in, when that file exists (see ``load_defaults``). Commands import what they
need when they run, so ``textkit --help`` stays fast.
"""

from __future__ import annotations

import argparse
import configparser
import importlib
import sys
from collections.abc import Callable, Sequence

# style -> (module, function), imported on first use.
CONVERTERS: dict[str, tuple[str, str]] = {
    "snake": ("textkit.case", "to_snake"),
    "camel": ("textkit.case", "to_camel"),
    "kebab": ("textkit.case", "to_kebab"),
    "title": ("textkit.case", "title_case"),
    "human": ("textkit.legacy_case", "humanize"),
}

CONFIG_FILE = "textkit.ini"
CONFIG_SECTION = "textkit"


def load_defaults(path: str = CONFIG_FILE) -> dict[str, str]:
    """The settings in the ``[textkit]`` section of ``path``, or ``{}`` without one.

    ``style`` is the default ``--style`` of ``textkit case`` and ``separator`` the word
    separator of ``textkit slug``. A missing file is not an error.
    """
    parser = configparser.ConfigParser()
    parser.read(path, encoding="utf-8")
    if not parser.has_section(CONFIG_SECTION):
        return {}
    return dict(parser[CONFIG_SECTION])


def converter(style: str) -> Callable[[str], str]:
    try:
        module_name, function_name = CONVERTERS[style]
    except KeyError:
        raise ValueError(f"unknown style: {style!r}") from None
    return getattr(importlib.import_module(module_name), function_name)


def _case(args: argparse.Namespace) -> int:
    convert = converter(args.style)
    for text in args.text:
        print(convert(text))
    return 0


def _slug(args: argparse.Namespace) -> int:
    from textkit.slug import slugify

    for text in args.text:
        print(slugify(text, separator=args.separator))
    return 0


def _labels(args: argparse.Namespace) -> int:
    from textkit.legacy_case import humanize

    for name in args.names:
        print(humanize(name))
    return 0


def build_parser() -> argparse.ArgumentParser:
    defaults = load_defaults()
    parser = argparse.ArgumentParser(prog="textkit")
    commands = parser.add_subparsers(dest="command", required=True)

    case = commands.add_parser("case", help="convert text between naming styles")
    case.add_argument("--style", choices=sorted(CONVERTERS), default=defaults.get("style", "snake"))
    case.add_argument("text", nargs="+")
    case.set_defaults(run=_case)

    slug = commands.add_parser("slug", help="turn text into URL slugs")
    slug.add_argument("--separator", default=defaults.get("separator", "-"))
    slug.add_argument("text", nargs="+")
    slug.set_defaults(run=_slug)

    labels = commands.add_parser("labels", help="turn column names into readable labels")
    labels.add_argument("names", nargs="+")
    labels.set_defaults(run=_labels)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())
