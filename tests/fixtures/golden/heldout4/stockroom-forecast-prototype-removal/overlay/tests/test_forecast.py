import pytest

from stockroom.forecast import forecast, moving_average


def test_moving_average_uses_the_last_window_days():
    assert moving_average([9, 9, 2, 4, 6, 8, 5, 3, 7]) == 5.0
    assert moving_average([4, 6], window=7) == 5.0
    assert moving_average([]) == 0.0


def test_forecast_rounds_up():
    assert forecast([3, 4, 4], days=7) == 26  # 3.67 a day


def test_window_must_be_positive():
    with pytest.raises(ValueError):
        moving_average([1, 2, 3], window=0)
