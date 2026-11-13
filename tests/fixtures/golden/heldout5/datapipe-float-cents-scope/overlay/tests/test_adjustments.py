from datapipe.adjustments import credit_cents, load_adjustments


def test_credit_cents():
    assert credit_cents("5.00") == 500
    assert credit_cents(" $2.50 ") == 250


def test_credits_for_one_order_add_up(tmp_path):
    path = tmp_path / "adjustments.csv"
    path.write_text("order_id,credit\nW-1,5.00\nW-2,$2.50\nW-1,1.25\n", encoding="utf-8")
    assert load_adjustments(path) == {"W-1": 625, "W-2": 250}
