"""The README's examples, run as doctests (scripts/check-docs.sh; CI runs it next to pytest)."""

import doctest
from pathlib import Path


def _repo_root() -> Path:
    """The directory holding pyproject.toml and README.md, wherever this file is run from."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file() and (parent / "README.md").is_file():
            return parent
    raise RuntimeError("cannot find the repository root")


README = _repo_root() / "README.md"


def test_readme_examples_run():
    result = doctest.testfile(str(README), module_relative=False, optionflags=doctest.ELLIPSIS)
    assert result.attempted > 0
    assert result.failed == 0, "a README example no longer matches the code (see the output above)"
