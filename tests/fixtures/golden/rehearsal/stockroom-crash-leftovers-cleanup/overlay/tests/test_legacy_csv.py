from stockroom.legacy_csv import load_spreadsheet


def test_load_spreadsheet_skips_rows_without_stock(tmp_path):
    path = tmp_path / "stock.csv"
    path.write_text("SKU,Name,Qty\nW-100 ,Widget,10\nG-200,Gadget,0\nL-2,Lamp,\n", encoding="utf-8")
    inventory = load_spreadsheet(path)
    assert inventory.skus() == ["W-100"]
    assert inventory.on_hand("W-100") == 10
