-- A reporting database as datapipe 0.3.0 left it: the 0.3.0 schema, five orders, two imports.
CREATE TABLE orders (
    order_id     TEXT PRIMARY KEY,
    email        TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    quantity     INTEGER NOT NULL,
    region       TEXT NOT NULL,
    created_at   TEXT NOT NULL
);
CREATE INDEX orders_by_email ON orders (email);
CREATE TABLE imports (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source        TEXT NOT NULL,
    rows_read     INTEGER NOT NULL,
    rows_inserted INTEGER NOT NULL
);

INSERT INTO orders VALUES ('L-1001', 'ana@example.com', 1250, 1, 'CA', '2026-09-01T08:00:00+00:00');
INSERT INTO orders VALUES ('L-1002', 'ben@example.com', 4000, 2, 'NY', '2026-09-01T09:15:00+00:00');
INSERT INTO orders VALUES ('L-1003', 'ana@example.com', -250, 1, 'CA', '2026-09-02T11:05:00+00:00');
INSERT INTO orders VALUES ('L-1004', 'cara@example.com', 725, 1, 'TX', '2026-09-02T17:45:00+00:00');
INSERT INTO orders VALUES ('L-1005', 'dev@example.com', 19999, 3, 'WA', '2026-09-03T10:00:00+00:00');

INSERT INTO imports (source, rows_read, rows_inserted) VALUES ('orders-2026-09-01.csv', 2, 2);
INSERT INTO imports (source, rows_read, rows_inserted) VALUES ('orders-2026-09-02.csv', 4, 3);
