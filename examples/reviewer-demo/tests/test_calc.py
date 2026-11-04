import pytest

from calc import add, mean


def test_add():
    assert add(2, 3) == 5


def test_mean():
    assert mean([1, 2, 3]) == 2


def test_mean_of_an_empty_list_is_an_error():
    with pytest.raises(ValueError):
        mean([])
