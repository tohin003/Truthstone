"""Invoices and their line items."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from ledger import discounts as discount_rules
from ledger import tax as tax_rules
from ledger.money import quantize


@dataclass
class LineItem:
    sku: str
    description: str
    quantity: int
    unit_price: Decimal

    def amount(self) -> Decimal:
        return quantize(self.unit_price * self.quantity)


@dataclass
class Invoice:
    number: str
    customer: str
    region: str
    items: list[LineItem] = field(default_factory=list)
    discounts: list[discount_rules.Discount] = field(default_factory=list)

    def subtotal(self) -> Decimal:
        return sum((item.amount() for item in self.items), Decimal("0"))

    def discount_total(self) -> Decimal:
        return discount_rules.apply(self.subtotal(), self.discounts)

    def taxable(self) -> Decimal:
        return self.subtotal() - self.discount_total()

    def tax(self) -> Decimal:
        """Tax on the discounted subtotal."""
        subtotal = self.subtotal()
        if not subtotal:
            return Decimal("0.00")
        share = self.taxable() / subtotal
        return sum(
            (tax_rules.tax_on(item.amount() * share, self.region) for item in self.items),
            Decimal("0.00"),
        )

    def total(self) -> Decimal:
        return quantize(self.taxable() + self.tax())
