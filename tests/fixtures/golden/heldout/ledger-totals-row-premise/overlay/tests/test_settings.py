from ledger import settings


def test_the_shipped_settings():
    assert settings.section("export")["delimiter"] == ","
    assert settings.section("reports")["top_customers"] == 3


def test_no_file_means_the_defaults(tmp_path):
    assert settings.load(tmp_path / "absent.toml") == {}


def test_a_missing_section_is_empty():
    assert settings.section("no-such-section") == {}
