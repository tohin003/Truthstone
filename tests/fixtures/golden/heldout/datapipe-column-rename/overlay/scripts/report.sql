-- Revenue per region, printed by `python -m datapipe report DATABASE.db`.
-- The Python side reads the columns region, orders and revenue_cents.
SELECT region,
       COUNT(*)          AS orders,
       SUM(amount_cents) AS revenue_cents
FROM orders
GROUP BY region
ORDER BY revenue_cents DESC, region;
