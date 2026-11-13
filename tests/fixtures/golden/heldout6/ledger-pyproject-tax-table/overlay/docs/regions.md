# Regions

The billing service sends one invoice per customer and region. Sales tax is looked up by the
region's two-letter code (`ledger.tax.rate_for`), case-insensitively; a region without a rate
raises `UnknownRegion`, and the invoice run stops there.

Supported today: California (CA), New York (NY), Texas (TX), Washington (WA) and Oregon (OR,
no sales tax since 0.4.1).

When billing starts in a new state, add its rate before the first invoice run.
