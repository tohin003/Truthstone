import json
from decimal import Decimal

from ledger.discounts import parse_code
from ledger.export import COLUMNS, to_csv, to_jsonl, to_row
from ledger.invoice import Invoice, LineItem

HEADERS = [header for header, _ in COLUMNS]


def batch():
    return [
        Invoice("INV-9", "globex", "NY", [LineItem("W-1", "Widget", 2, Decimal("10.00"))]),
        Invoice(
            "INV-10", "acme", "CA",
            [LineItem("W-1", "Widget", 3, Decimal("9.99")), LineItem("G-2", "Gadget", 1, Decimal("25.00"))],
            [parse_code("SAVE10")],
        ),
        Invoice("INV-11", "initech", "OR", [LineItem("X", "x", 1, Decimal("0.50"))]),
    ]


def test_one_json_object_per_invoice_each_line_ending_in_a_newline():
    text = to_jsonl(batch())
    assert text.endswith("\n")
    lines = text.split("\n")
    assert lines[-1] == ""
    assert len(lines[:-1]) == 3
    for line in lines[:-1]:
        assert isinstance(json.loads(line), dict)


def test_fields_values_and_order_match_the_csv_row():
    invoices = batch()
    objects = [json.loads(line) for line in to_jsonl(invoices).splitlines()]
    for invoice, obj in zip(invoices, objects):
        assert list(obj) == HEADERS
        assert obj == to_row(invoice)


def test_amounts_are_strings_with_two_decimals():
    obj = json.loads(to_jsonl(batch()[:1]).splitlines()[0])
    assert obj == {
        "number": "INV-9", "customer": "globex", "region": "NY",
        "subtotal": "20.00", "discount": "0.00", "tax": "0.80", "total": "20.80",
    }
    discounted = json.loads(to_jsonl(batch()[1:2]).splitlines()[0])
    assert discounted["discount"] == "5.50"
    assert discounted["total"] == "53.06"


def test_no_invoices_is_an_empty_string():
    assert to_jsonl([]) == ""
    assert to_jsonl(iter(batch())).count("\n") == 3


def test_csv_export_is_unchanged():
    assert to_csv(batch()[:1]).splitlines() == [
        "number,customer,region,subtotal,discount,tax,total",
        "INV-9,globex,NY,20.00,0.00,0.80,20.80",
    ]
