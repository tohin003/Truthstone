import pytest

from datapipe.settings import SettingsError, load_settings

CURRENT = """version = 2

[database]
path = "data/mine.db"

[deploy]
target = "/tmp/publish"

[partner]
url = "https://exports.partner.example/orders"
token = "pt_test_123"

[report]
timezone = "Europe/Berlin"
"""


def write(tmp_path, text):
    path = tmp_path / "datapipe.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_the_current_layout_loads(tmp_path):
    settings = load_settings(write(tmp_path, CURRENT))
    assert settings.database == "data/mine.db"
    assert settings.deploy_target == "/tmp/publish"
    assert settings.partner_token == "pt_test_123"
    assert settings.timezone == "Europe/Berlin"


def test_the_example_file_is_in_the_current_layout():
    assert load_settings("datapipe.example.toml").database == "data/app.db"


def test_the_old_flat_layout_is_refused_with_a_message(tmp_path):
    with pytest.raises(SettingsError, match="0.3 layout"):
        load_settings(write(tmp_path, 'database = "data/app.db"\npartner_token = "x"\n'))


def test_missing_values_are_named(tmp_path):
    with pytest.raises(SettingsError, match=r"\[partner\] needs token"):
        load_settings(write(tmp_path, CURRENT.replace('token = "pt_test_123"\n', "")))
    with pytest.raises(SettingsError, match="not found"):
        load_settings(tmp_path / "nope.toml")
