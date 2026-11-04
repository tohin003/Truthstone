import pytest

import textkit


def test_legacy_names_are_still_reachable_from_the_package():
    assert textkit.camelize("hello_world") == "HelloWorld"
    assert textkit.underscore("createdAt") == "created_at"
    with pytest.raises(AttributeError):
        textkit.no_such_helper  # noqa: B018
