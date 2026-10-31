"""Products, categories and promotions."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from decimal import Decimal

from emporio_agent.domain import Category, Product, ProductStatus, Promotion
from emporio_agent.money import from_cents, to_cents
from emporio_agent.text import compact, search_tokens

# Effective price = promotional price when an active promotion exists. Computed in SQL so that
# price filters and ordering consider promotions (a R$ 1.200 item at 20% off is "up to R$ 1.000").
# ROUND() in SQLite rounds half away from zero, i.e. half-up for positive values, matching
# money.apply_discount.
_EFFECTIVE_CENTS = (
    "CASE WHEN pr.discount_percent IS NULL THEN p.price_cents "
    "ELSE CAST(ROUND(p.price_cents * (100 - pr.discount_percent) / 100.0) AS INTEGER) END"
)

_SELECT_PRODUCT = f"""
SELECT p.*, c.name AS category_name,
       pr.promotion_id, pr.discount_percent, pr.description AS promotion_description,
       {_EFFECTIVE_CENTS} AS effective_cents
FROM products p
JOIN categories c ON c.category_id = p.category_id
LEFT JOIN promotions pr ON pr.product_id = p.product_id AND pr.is_active = 1
"""


@dataclass(frozen=True)
class ProductPage:
    items: list[Product]
    total: int


def _product(row: sqlite3.Row) -> Product:
    promotion = None
    if row["promotion_id"] is not None:
        promotion = Promotion(
            promotion_id=row["promotion_id"],
            product_id=row["product_id"],
            discount_percent=row["discount_percent"],
            description=row["promotion_description"],
            is_active=True,
        )
    return Product(
        product_id=row["product_id"],
        name=row["name"],
        category_id=row["category_id"],
        category_name=row["category_name"],
        description=row["description"],
        price=from_cents(row["price_cents"]),
        stock_quantity=row["stock_quantity"],
        status=ProductStatus(row["status"]),
        specs=json.loads(row["specs_json"]),
        active_promotion=promotion,
    )


class CatalogRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def categories(self) -> list[Category]:
        rows = self._conn.execute(
            "SELECT category_id, name, description FROM categories ORDER BY category_id"
        )
        return [Category(r["category_id"], r["name"], r["description"]) for r in rows]

    def category_product_counts(self) -> dict[int, int]:
        rows = self._conn.execute(
            "SELECT category_id, COUNT(*) AS n FROM products "
            "WHERE status = 'active' AND stock_quantity > 0 GROUP BY category_id"
        )
        return {r["category_id"]: r["n"] for r in rows}

    def get(self, product_id: int) -> Product | None:
        row = self._conn.execute(
            f"{_SELECT_PRODUCT} WHERE p.product_id = ?", (product_id,)
        ).fetchone()
        return _product(row) if row else None

    def search(
        self,
        *,
        text: str | None = None,
        category_id: int | None = None,
        min_price: Decimal | None = None,
        max_price: Decimal | None = None,
        sellable_only: bool = True,
        limit: int = 10,
        offset: int = 0,
    ) -> ProductPage:
        where: list[str] = []
        params: list[object] = []
        for token in search_tokens(text or ""):
            # Every token must appear (AND), so adding words narrows the result.
            where.append("p.search_compact LIKE ?")
            params.append(f"%{token}%")
        if category_id is not None:
            where.append("p.category_id = ?")
            params.append(category_id)
        if sellable_only:
            where.append("p.status = 'active' AND p.stock_quantity > 0")
        if min_price is not None:
            where.append(f"{_EFFECTIVE_CENTS} >= ?")
            params.append(to_cents(min_price))
        if max_price is not None:
            where.append(f"{_EFFECTIVE_CENTS} <= ?")
            params.append(to_cents(max_price))
        clause = f"WHERE {' AND '.join(where)}" if where else ""

        total = self._conn.execute(
            "SELECT COUNT(*) FROM products p "
            "LEFT JOIN promotions pr ON pr.product_id = p.product_id AND pr.is_active = 1 "
            f"{clause}",
            params,
        ).fetchone()[0]
        rows = self._conn.execute(
            f"{_SELECT_PRODUCT} {clause} ORDER BY effective_cents, p.product_id LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
        return ProductPage([_product(r) for r in rows], total)

    def find_by_name(self, name: str, limit: int = 5) -> list[Product]:
        """Exact compact-name match first; otherwise products whose name contains every token."""
        key = compact(name)
        if not key:
            return []
        rows = self._conn.execute(f"{_SELECT_PRODUCT} WHERE p.name_compact = ?", (key,)).fetchall()
        if rows:
            return [_product(r) for r in rows]
        tokens = search_tokens(name)
        where = " AND ".join("p.name_compact LIKE ?" for _ in tokens)
        rows = self._conn.execute(
            f"{_SELECT_PRODUCT} WHERE {where} ORDER BY p.product_id LIMIT ?",
            [*(f"%{t}%" for t in tokens), limit],
        ).fetchall()
        return [_product(r) for r in rows]

    def alternatives(self, product: Product, limit: int = 3) -> list[Product]:
        """Sellable products of the same category, closest in effective price."""
        target = to_cents(product.price)
        rows = self._conn.execute(
            f"{_SELECT_PRODUCT} WHERE p.category_id = ? AND p.product_id <> ? "
            "AND p.status = 'active' AND p.stock_quantity > 0 "
            "ORDER BY ABS(effective_cents - ?), p.product_id LIMIT ?",
            (product.category_id, product.product_id, target, limit),
        ).fetchall()
        return [_product(r) for r in rows]

    def inactive_promotions(self, product_id: int) -> list[Promotion]:
        rows = self._conn.execute(
            "SELECT * FROM promotions WHERE product_id = ? AND is_active = 0 ORDER BY promotion_id",
            (product_id,),
        )
        return [
            Promotion(
                r["promotion_id"], r["product_id"], r["discount_percent"], r["description"], False
            )
            for r in rows
        ]
