"""Writes the generated SQLite catalog. Only type normalization and derived search columns."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from emporio_agent.ingest.sources import SourceData
from emporio_agent.money import to_cents
from emporio_agent.text import compact, digits, normalize

SCHEMA = """
CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE categories (
    category_id INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT NOT NULL,
    name_norm   TEXT NOT NULL
);

CREATE TABLE products (
    product_id     INTEGER PRIMARY KEY,
    name           TEXT NOT NULL,
    category_id    INTEGER NOT NULL REFERENCES categories(category_id),
    description    TEXT NOT NULL,
    price_cents    INTEGER NOT NULL CHECK (price_cents > 0),
    stock_quantity INTEGER NOT NULL CHECK (stock_quantity >= 0),
    status         TEXT NOT NULL CHECK (status IN ('active', 'discontinued', 'coming_soon')),
    specs_json     TEXT NOT NULL,
    created_at     TEXT NOT NULL,
    name_compact   TEXT NOT NULL,
    search_compact TEXT NOT NULL
);
CREATE INDEX ix_products_category_status_price ON products(category_id, status, price_cents);
CREATE INDEX ix_products_status_price ON products(status, price_cents);

CREATE TABLE promotions (
    promotion_id     INTEGER PRIMARY KEY,
    product_id       INTEGER NOT NULL REFERENCES products(product_id),
    discount_percent INTEGER NOT NULL CHECK (discount_percent BETWEEN 1 AND 99),
    description      TEXT NOT NULL,
    is_active        INTEGER NOT NULL CHECK (is_active IN (0, 1))
);
CREATE INDEX ix_promotions_product_active ON promotions(product_id, is_active);

CREATE TABLE customers (
    customer_id  INTEGER PRIMARY KEY,
    name         TEXT NOT NULL,
    phone        TEXT NOT NULL,
    email        TEXT NOT NULL,
    city         TEXT NOT NULL,
    phone_digits TEXT NOT NULL,
    email_norm   TEXT NOT NULL
);
CREATE INDEX ix_customers_phone ON customers(phone_digits);
CREATE INDEX ix_customers_email ON customers(email_norm);

CREATE TABLE orders (
    order_id           INTEGER PRIMARY KEY,
    customer_id        INTEGER NOT NULL REFERENCES customers(customer_id),
    order_date         TEXT NOT NULL,
    status             TEXT NOT NULL
                       CHECK (status IN ('pending','confirmed','shipped','delivered','cancelled')),
    total_cents        INTEGER NOT NULL,
    payment_method     TEXT NOT NULL,
    tracking_code      TEXT,
    estimated_delivery TEXT,
    notes              TEXT
);
CREATE INDEX ix_orders_customer ON orders(customer_id);

CREATE TABLE order_items (
    order_id   INTEGER NOT NULL REFERENCES orders(order_id),
    product_id INTEGER NOT NULL REFERENCES products(product_id),
    quantity   INTEGER NOT NULL CHECK (quantity > 0)
);
CREATE INDEX ix_order_items_order ON order_items(order_id);
"""


def build_catalog(src: SourceData, db_path: Path, metadata: dict[str, str]) -> None:
    """Builds into a temporary file and swaps it in, so a failed build never leaves a half DB."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = db_path.with_suffix(".tmp")
    tmp_path.unlink(missing_ok=True)
    categories = {c.category_id: c for c in src.categories}

    conn = sqlite3.connect(tmp_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(SCHEMA)
        conn.executemany("INSERT INTO metadata VALUES (?, ?)", sorted(metadata.items()))
        conn.executemany(
            "INSERT INTO categories VALUES (?, ?, ?, ?)",
            [(c.category_id, c.name, c.description, normalize(c.name)) for c in src.categories],
        )
        conn.executemany(
            "INSERT INTO products VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    p.product_id,
                    p.name,
                    p.category_id,
                    p.description,
                    to_cents(p.price),
                    p.stock_quantity,
                    p.status,
                    json.dumps(p.specs, ensure_ascii=False),
                    p.created_at.isoformat(),
                    compact(p.name),
                    compact(
                        " ".join(
                            [
                                p.name,
                                categories[p.category_id].name,
                                p.description,
                                *p.specs.values(),
                            ]
                        )
                    ),
                )
                for p in src.products
            ],
        )
        conn.executemany(
            "INSERT INTO promotions VALUES (?, ?, ?, ?, ?)",
            [
                (p.promotion_id, p.product_id, p.discount_percent, p.description, int(p.is_active))
                for p in src.promotions
            ],
        )
        conn.executemany(
            "INSERT INTO customers VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    c.customer_id,
                    c.name,
                    c.phone,
                    c.email,
                    c.city,
                    digits(c.phone),
                    normalize(c.email),
                )
                for c in src.customers
            ],
        )
        conn.executemany(
            "INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    o.order_id,
                    o.customer_id,
                    o.order_date.isoformat(),
                    o.status,
                    to_cents(o.total),
                    o.payment_method,
                    o.tracking_code,
                    o.estimated_delivery.isoformat() if o.estimated_delivery else None,
                    o.notes,
                )
                for o in src.orders
            ],
        )
        conn.executemany(
            "INSERT INTO order_items VALUES (?, ?, ?)",
            [(i.order_id, i.product_id, i.quantity) for i in src.order_items],
        )
        conn.commit()
    finally:
        conn.close()
    tmp_path.replace(db_path)
