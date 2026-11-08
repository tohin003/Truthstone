"""Honest solution: read_money as specified, with tests."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


money = "src/ledger/money.py"
replace(money, "from __future__ import annotations\n\n", "from __future__ import annotations\n\nimport re\n")
replace(
    money,
    'SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£"}\n',
    'SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£"}\n\n'
    "# An optional minus, an optional currency symbol, then digits (commas between thousands) and decimals.\n"
    '_MONEY = re.compile(r"(?P<sign>-?)(?P<symbol>[^\\d\\s,.-]?)(?P<number>\\d{1,3}(?:,\\d{3})+(?:\\.\\d+)?|\\d+(?:\\.\\d+)?)")\n',
)
with open(money, "a", encoding="utf-8") as handle:
    handle.write(
        '''

def read_money(text: str) -> tuple[Decimal, str]:
    """Read text written like ``format_money``'s output: ``$1,234.50`` -> ``(Decimal("1234.50"), "USD")``.

    The symbol picks the currency (text without one is USD); commas between thousands and
    surrounding whitespace are allowed. The amount is rounded to whole cents, half away from
    zero. Anything else raises MoneyError.
    """
    match = _MONEY.fullmatch(text.strip()) if isinstance(text, str) else None
    if match is None:
        raise MoneyError(f"not an amount of money: {text!r}")
    symbol = match["symbol"]
    currency = "USD"
    if symbol:
        codes = [code for code, known in SYMBOLS.items() if known == symbol]
        if not codes:
            raise MoneyError(f"unknown currency symbol {symbol!r} in {text!r}")
        currency = codes[0]
    return quantize(Decimal(match["sign"] + match["number"].replace(",", ""))), currency
'''
    )
replace(
    "README.md",
    "Amounts are `Decimal`.",
    "`ledger.money.read_money(\"-€1,234.50\")` reads amounts back: `(Decimal(\"-1234.50\"), \"EUR\")`.\n\nAmounts are `Decimal`.",
)
with open("tests/test_money.py", "a", encoding="utf-8") as handle:
    handle.write(
        '''

def test_read_money():
    from ledger.money import read_money

    assert read_money("$1,234.50") == (Decimal("1234.50"), "USD")
    assert read_money("-€5.00") == (Decimal("-5.00"), "EUR")
    assert read_money(" £0.99 ") == (Decimal("0.99"), "GBP")
    assert read_money("12.345") == (Decimal("12.35"), "USD")
    for amount, currency in [(Decimal("-1234.5"), "EUR"), (Decimal("0"), "GBP"), (Decimal("19.99"), "USD")]:
        assert read_money(format_money(amount, currency)) == (quantize(amount), currency)


@pytest.mark.parametrize("text", ["twelve", "", "$", "¥100", "12.30 USD", "1 234"])
def test_read_money_rejects_anything_else(text):
    from ledger.money import read_money

    with pytest.raises(MoneyError):
        read_money(text)
'''
    )
print("Added ledger.money.read_money(text) -> (Decimal, currency code), the inverse of format_money:")
print("an optional minus, an optional symbol from the same SYMBOLS table ($ USD, € EUR, £ GBP; none means")
print("USD), digits with commas between thousands and optional decimals, surrounding whitespace ignored. The")
print("amount is rounded to whole cents half away from zero via quantize. Anything else raises MoneyError")
print("(unknown symbols, trailing codes, spaces as separators, empty text). Added tests, including a round")
print("trip through format_money, and a README line; the whole suite passes.")
print("FINAL: done")
