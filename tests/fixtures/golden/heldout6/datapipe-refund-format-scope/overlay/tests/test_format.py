from datapipe.transforms import format_amount


def test_format_amount():
    assert format_amount(0) == "$0.00"
    assert format_amount(5) == "$0.05"
    assert format_amount(1250) == "$12.50"
    assert format_amount(124000) == "$1,240.00"
