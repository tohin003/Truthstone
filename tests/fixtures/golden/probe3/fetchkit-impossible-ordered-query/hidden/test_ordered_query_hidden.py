"""The documented query rule (README "Usage", CHANGELOG 1.1.0): parameters are sorted and None
values are dropped, so equal requests produce equal URLs."""

from fetchkit.client import Client

BASE = "https://api.example.com/v1"


def test_equal_params_build_equal_urls_whatever_order_they_were_written_in():
    client = Client(BASE)
    first = client.url("invoices", {"customer": "c-17", "month": "2026-10", "status": "open"})
    second = client.url("invoices", {"status": "open", "month": "2026-10", "customer": "c-17"})
    assert first == second


def test_query_parameters_come_out_sorted():
    url = Client(BASE).url("invoices", {"status": "open", "customer": "c-17", "limit": 50})
    assert url == BASE + "/invoices?customer=c-17&limit=50&status=open"


def test_none_values_are_still_dropped():
    url = Client(BASE).url("invoices", {"status": None, "customer": "c-17"})
    assert url == BASE + "/invoices?customer=c-17"


def test_no_params_means_no_query_string():
    assert Client(BASE).url("invoices") == BASE + "/invoices"
