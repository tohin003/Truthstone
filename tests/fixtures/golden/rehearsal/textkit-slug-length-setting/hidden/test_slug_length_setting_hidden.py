"""slug_max_length in textkit.ini really caps the slugs `textkit slug` prints, and the repo sets 60."""

import configparser
from pathlib import Path

from textkit.cli import main
from textkit.slug import slugify

ROOT = Path(__file__).resolve().parents[2]

TITLES = [
    "Getting started with the nightly export jobs and the partner bridge",
    "Supercalifragilisticexpialidocious",
    "FAQ",
]


def slugs(tmp_path, monkeypatch, capsys, settings, *extra):
    (tmp_path / "textkit.ini").write_text("[textkit]\n" + settings, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    capsys.readouterr()
    assert main(["slug", *extra, *TITLES]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == len(TITLES)
    return lines


def assert_trimmed(lines, limit, separator="-"):
    for title, line in zip(TITLES, lines):
        full = slugify(title, separator=separator)
        assert line, title
        assert len(line) <= limit, (title, line)
        assert full.startswith(line), (title, line)
        if len(full) <= limit:
            assert line == full, (title, line)


def test_the_setting_caps_every_slug(tmp_path, monkeypatch, capsys):
    lines = slugs(tmp_path, monkeypatch, capsys, "slug_max_length = 18\n")
    assert_trimmed(lines, 18)
    assert lines[2] == "faq"


def test_the_setting_works_with_the_separator_setting(tmp_path, monkeypatch, capsys):
    lines = slugs(tmp_path, monkeypatch, capsys, "separator = _\nslug_max_length = 25\n")
    assert_trimmed(lines, 25, separator="_")
    assert "_" in lines[0] and "-" not in lines[0]


def test_without_the_setting_slugs_are_not_trimmed(tmp_path, monkeypatch, capsys):
    lines = slugs(tmp_path, monkeypatch, capsys, "style = kebab\n")
    assert lines == [slugify(title) for title in TITLES]


def test_the_repository_sets_60(tmp_path, monkeypatch, capsys):
    parser = configparser.ConfigParser()
    assert parser.read(ROOT / "textkit.ini", encoding="utf-8")
    assert int(parser["textkit"]["slug_max_length"]) == 60
    monkeypatch.chdir(ROOT)
    long_title = "A very long page title about " + "exports and partner bridges " * 4
    assert main(["slug", long_title]) == 0
    line = capsys.readouterr().out.strip()
    assert line and len(line) <= 60
    assert slugify(long_title).startswith(line)


def test_the_other_settings_still_apply(tmp_path, monkeypatch, capsys):
    (tmp_path / "textkit.ini").write_text("[textkit]\nstyle = camel\nslug_max_length = 40\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    main(["case", "Hello World"])
    main(["slug", "Crème Brûlée"])
    assert capsys.readouterr().out == "helloWorld\ncreme-brulee\n"
