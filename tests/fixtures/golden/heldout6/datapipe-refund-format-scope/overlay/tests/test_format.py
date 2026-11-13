from datapipe.transforms import format_dollars


def test_format_dollars():
    assert format_dollars(0) == "$0.00"
    assert format_dollars(5) == "$0.05"
    assert format_dollars(1250) == "$12.50"
    assert format_dollars(124000) == "$1,240.00"
