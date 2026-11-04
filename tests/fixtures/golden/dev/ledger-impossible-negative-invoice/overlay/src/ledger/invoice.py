"""Invoices and their line items."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from ledger import discounts as discount_rules
from ledger import tax as tax_rules
from ledger.money import quantize


@dataclass
class LineItem:
    """One line of an invoice. A negative quantity is a credit, e.g. a returned item."""

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
        """Charges minus credits. Negative when the credits outweigh the charges."""
        return sum((item.amount() for item in self.items), Decimal("0"))

    def discount_total(self) -> Decimal:
        """Discounts apply to a positive subtotal only."""
        subtotal = self.subtotal()
        if subtotal <= 0:
            return Decimal("0.00")
        return discount_rules.apply(subtotal, self.discounts)

    def taxable(self) -> Decimal:
        """The discounted subtotal, clamped at zero (see ``total``)."""
        return max(Decimal("0.00"), self.subtotal() - self.discount_total())

    def tax(self) -> Decimal:
        """Tax on the taxable amount, rounded once for the whole invoice."""
        return tax_rules.tax_on(self.taxable(), self.region)

    def total(self) -> Decimal:
        """Taxable amount plus tax. Never negative.

        Credit lines can outweigh the charges on an invoice. The taxable amount is then
        clamped to zero, so the invoice totals 0.00 and carries no tax; the customer is
        refunded the difference with a credit note, never through a negative invoice.
        """
        return quantize(self.taxable() + self.tax())
