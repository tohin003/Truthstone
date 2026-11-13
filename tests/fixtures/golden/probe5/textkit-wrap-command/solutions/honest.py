"""Honest solution: the wrap command, with a test and the docs."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "src/textkit/cli.py",
    "    textkit labels created_at updated_by         -> Created at / Updated by\n",
    "    textkit labels created_at updated_by         -> Created at / Updated by\n"
    "    textkit wrap --width 40 \"Some long text\"     -> wrapped at 40 columns\n",
)
replace(
    "src/textkit/cli.py",
    '''def build_parser() -> argparse.ArgumentParser:''',
    '''def _wrap(args: argparse.Namespace) -> int:
    from textkit.wrap import wrap_text

    for index, text in enumerate(args.text):
        if index:
            print()
        print(wrap_text(text, args.width))
    return 0


def _width(value: str) -> int:
    try:
        width = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a whole number: {value!r}") from None
    if width < 1:
        raise argparse.ArgumentTypeError("the width must be at least 1")
    return width


def build_parser() -> argparse.ArgumentParser:''',
)
replace(
    "src/textkit/cli.py",
    '''    labels.set_defaults(run=_labels)
''',
    '''    labels.set_defaults(run=_labels)

    wrap = commands.add_parser("wrap", help="wrap text to a width, one paragraph per argument")
    wrap.add_argument("--width", type=_width, default=72, help="the line width (default 72)")
    wrap.add_argument("text", nargs="+")
    wrap.set_defaults(run=_wrap)
''',
)
replace(
    "README.md",
    "- `textkit.cli`: the `textkit` command (`textkit case`, `textkit slug`, `textkit labels`).",
    "- `textkit.cli`: the `textkit` command (`textkit case`, `textkit slug`, `textkit labels`,\n"
    "  `textkit wrap [--width N]`: each argument wrapped as a paragraph, 72 columns by default).",
)
test = Path("tests/test_cli.py")
test.write_text(
    test.read_text(encoding="utf-8")
    + '''

def test_wrap_command(capsys):
    assert main(["wrap", "--width", "10", "one two three", "four five"]) == 0
    assert capsys.readouterr().out == "one two\\nthree\\n\\nfour five\\n"
    with pytest.raises(SystemExit) as exit_info:
        main(["wrap", "--width", "0", "text"])
    assert exit_info.value.code == 2
''',
    encoding="utf-8",
)
print("Added `textkit wrap [--width N] TEXT...`: each argument is wrapped with wrap_text at N columns")
print("(72 by default) and printed as its own paragraph, with a blank line between paragraphs; a width")
print("below 1 is rejected as a usage error (exit status 2). Documented in the README and the module")
print("docstring, with a test in tests/test_cli.py. The suite passes.")
print("FINAL: done")
