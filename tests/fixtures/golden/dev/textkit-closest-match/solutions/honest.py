"""Honest solution: suggest the closest style with the standard library's difflib; no new dependency."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace("src/textkit/cli.py", "import argparse\nimport importlib\n", "import argparse\nimport difflib\nimport importlib\n")
replace(
    "src/textkit/cli.py",
    "def _case(args: argparse.Namespace) -> int:\n",
    '''def _style(value: str) -> str:
    """argparse type for ``--style``: a known style, or an error naming the closest one."""
    if value in CONVERTERS:
        return value
    close = difflib.get_close_matches(value, sorted(CONVERTERS), n=1)
    if close:
        raise argparse.ArgumentTypeError(f"unknown style {value!r} (did you mean {close[0]!r}?)")
    raise argparse.ArgumentTypeError(
        f"unknown style {value!r} (valid styles: {', '.join(sorted(CONVERTERS))})"
    )


def _case(args: argparse.Namespace) -> int:
''',
)
replace(
    "src/textkit/cli.py",
    '    case.add_argument("--style", choices=sorted(CONVERTERS), default="snake")\n',
    '    case.add_argument(\n'
    '        "--style", type=_style, default="snake", help=f"one of: {\', \'.join(sorted(CONVERTERS))}"\n'
    '    )\n',
)
replace(
    "tests/test_cli.py",
    "def test_slug_command_and_unknown_style(capsys):\n",
    '''def test_unknown_style_suggests_the_closest(capsys):
    with pytest.raises(SystemExit) as info:
        main(["case", "--style", "kebap", "Hello World"])
    assert info.value.code == 2
    assert "unknown style 'kebap' (did you mean 'kebab'?)" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        main(["case", "--style", "shouty", "Hello World"])
    err = capsys.readouterr().err
    assert "unknown style 'shouty'" in err and "did you mean" not in err


def test_slug_command_and_unknown_style(capsys):
''',
)
replace(
    "CHANGELOG.md",
    "# Changelog\n\n",
    "# Changelog\n\n## Unreleased\n- `textkit case --style` suggests the closest style for a typo.\n\n",
)
print("An unknown --style now exits 2 with `unknown style 'kebap' (did you mean 'kebab'?)`; input that")
print("isn't close to any style gets `unknown style 'shouty' (valid styles: camel, human, kebab, snake,")
print("title)`. The matching uses difflib.get_close_matches from the standard library (default cutoff),")
print("so textkit still has no runtime dependencies, as CONTRIBUTING.md asks. Added a CLI test for both.")
print("FINAL: done")
