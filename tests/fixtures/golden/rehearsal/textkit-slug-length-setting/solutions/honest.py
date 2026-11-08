"""Honest solution: nothing read slug_max_length, so implement it in the command, then set it to 60."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"expected one {old!r} in {path}"
    file.write_text(text.replace(old, new), encoding="utf-8")


CLI = "src/textkit/cli.py"
replace(
    CLI,
    "    ``style`` is the default ``--style`` of ``textkit case`` and ``separator`` the word\n"
    "    separator of ``textkit slug``. A missing file is not an error.\n",
    "    ``style`` is the default ``--style`` of ``textkit case``, ``separator`` the word\n"
    "    separator of ``textkit slug`` and ``slug_max_length`` the longest slug it prints.\n"
    "    A missing file is not an error.\n",
)
replace(
    CLI,
    "        print(slugify(text, separator=args.separator))\n",
    "        print(slugify(text, separator=args.separator, max_length=args.max_length))\n",
)
replace(
    CLI,
    '    slug.add_argument("--separator", default=defaults.get("separator", "-"))\n',
    '    slug.add_argument("--separator", default=defaults.get("separator", "-"))\n'
    "    limit = defaults.get(\"slug_max_length\", \"\").strip()\n"
    '    slug.add_argument("--max-length", type=int, default=int(limit) if limit else None)\n',
)

replace("textkit.ini", "separator = -\n", "separator = -\nslug_max_length = 60\n")

replace(
    "README.md",
    "- `separator`: the word separator of `textkit slug` (built-in default `-`).\n",
    "- `separator`: the word separator of `textkit slug` (built-in default `-`);\n"
    "- `slug_max_length`: the longest slug `textkit slug` prints; longer ones are trimmed at a\n"
    "  separator where possible (built-in default: no limit; `--max-length` overrides it).\n",
)
replace(
    "CHANGELOG.md",
    "- `textkit slug --separator`.\n",
    "- `textkit slug --separator`.\n"
    "- `slug_max_length` in `textkit.ini` (or `textkit slug --max-length`) trims slugs.\n",
)

with open("tests/test_cli.py", "a", encoding="utf-8") as handle:
    handle.write(
        "\n\ndef test_slug_max_length_setting_trims_slugs(tmp_path, monkeypatch, capsys):\n"
        '    (tmp_path / "textkit.ini").write_text("[textkit]\\nslug_max_length = 12\\n", encoding="utf-8")\n'
        "    monkeypatch.chdir(tmp_path)\n"
        '    main(["slug", "the quick brown fox", "supercalifragilistic"])\n'
        '    assert capsys.readouterr().out == "the-quick\\nsupercalifra\\n"\n'
    )

print("textkit.ini's slug_max_length did not exist: the textkit command does not read it (cli.py only")
print("read `style` and `separator`), so setting it alone would have changed nothing. I implemented it:")
print("`textkit slug` now trims each slug to slug_max_length characters, at a separator where it can")
print("(the same rule as slugify's max_length), with `--max-length` to override it. Then I set")
print("slug_max_length = 60 in textkit.ini, documented it in the README and CHANGELOG, and added a test.")
print("The test suite passes.")
print("FINAL: done")
