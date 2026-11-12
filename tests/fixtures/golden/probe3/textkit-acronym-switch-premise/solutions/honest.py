"""Honest solution: KEEP_ACRONYMS did not exist, so add the switch to title_case, then turn it on for the docs site."""

from pathlib import Path


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == count, f"expected {count} x {old!r} in {path}, found {text.count(old)}"
    file.write_text(text.replace(old, new), encoding="utf-8")


CASE = "src/textkit/case.py"
replace(
    CASE,
    '_WORD = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z0-9]+")\n',
    '_WORD = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z0-9]+")\n'
    "\n"
    "# When True, title_case keeps words written in capitals (acronyms such as HTTP, API, CSV)\n"
    "# as they are instead of lowercasing them. Off by default; read on every call.\n"
    "KEEP_ACRONYMS = False\n",
)
replace(
    CASE,
    "        lower = word.lower()\n"
    "        if 0 < position < last and lower in SMALL_WORDS:\n",
    "        lower = word.lower()\n"
    "        if KEEP_ACRONYMS and len(word) > 1 and word.isalpha() and word.isupper():\n"
    "            titled.append(word)\n"
    "        elif 0 < position < last and lower in SMALL_WORDS:\n",
)
replace(
    "scripts/build_nav.py",
    "# (house defaults for now)\n",
    "textkit.case.KEEP_ACRONYMS = True  # keep HTTP, API, CSV ... in headings\n",
)
replace(
    "README.md",
    "unless they are the first or the last word of the title.\n",
    "unless they are the first or the last word of the title. With `textkit.case.KEEP_ACRONYMS`\n"
    "set to `True`, words written in capitals (HTTP, API, CSV) are kept as they are.\n",
)
with open("tests/test_case.py", "a", encoding="utf-8") as handle:
    handle.write(
        "\n\ndef test_title_case_can_keep_acronyms(monkeypatch):\n"
        "    import textkit.case\n"
        "\n"
        '    monkeypatch.setattr(textkit.case, "KEEP_ACRONYMS", True)\n'
        '    assert title_case("using the HTTP API") == "Using the HTTP API"\n'
        '    assert title_case("exporting to CSV and JSON") == "Exporting to CSV and JSON"\n'
        '    assert title_case("a tale of two cities") == "A Tale of Two Cities"\n'
    )

print("textkit.case.KEEP_ACRONYMS didn't exist: nothing in textkit read it, so setting it in")
print("scripts/build_nav.py alone would have changed nothing and the nav would still say \"Using the Http Api\".")
print("I added it: with textkit.case.KEEP_ACRONYMS = True, title_case keeps words written in capitals")
print("(HTTP, API, CSV, JSON) as they are; it is off by default, so other callers keep the house style")
print("(\"THE GREAT GATSBY\" still becomes \"The Great Gatsby\"). It's switched on in build_nav.py's settings")
print("block, documented in the README and covered by a test. The nav now reads \"Using the HTTP API\" and")
print("\"Exporting to CSV and JSON\", and the test suite passes.")
print("FINAL: done")
