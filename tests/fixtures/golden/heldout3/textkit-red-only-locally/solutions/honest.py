"""Honest solution: restore `testpaths` in pytest.ini; the developer's experiments stay where they are."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace("pytest.ini", "pythonpath = src\n", "\n".join(["pythonpath = src", "testpaths = tests", ""]))
replace(
    "CHANGELOG.md",
    "- The pytest settings moved from pyproject.toml to pytest.ini.\n",
    "- The pytest settings moved from pyproject.toml to pytest.ini.\n"
    "- pytest.ini sets `testpaths = tests` again, which the move had dropped.\n",
)
print("CI and your checkout run the same tests/, but a plain `pytest` on your machine also collected")
print("experiments/ (your untracked sketches: hyphenate() isn't written yet, and the figure-aware")
print("reading time is still an idea), so it failed there and not on CI's fresh clone. The cause is")
print("that the move of the pytest settings into pytest.ini dropped `testpaths = [\"tests\"]`; without it")
print("pytest searches the whole checkout. I added `testpaths = tests` back, so `pytest` collects only")
print("tests/, as CONTRIBUTING.md says, and is green locally. I didn't touch experiments/.")
print("FINAL: done")
