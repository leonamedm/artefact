"""Catalog queries and availability rules (manual §7.3)."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from emporio_agent.domain import Category, Product, ProductStatus, Promotion
from emporio_agent.repositories.catalog import CatalogRepository, ProductPage
from emporio_agent.text import normalize

MAX_PAGE_SIZE = 20


class Availability(StrEnum):
    AVAILABLE = "available"
    OUT_OF_STOCK = "out_of_stock"
    DISCONTINUED = "discontinued"
    COMING_SOON = "coming_soon"


def availability(product: Product) -> Availability:
    # Status wins over stock: a discontinued item with units left is not offered, and a
    # coming-soon item is not sellable before launch (docs/data-findings.md).
    if product.status is ProductStatus.DISCONTINUED:
        return Availability.DISCONTINUED
    if product.status is ProductStatus.COMING_SOON:
        return Availability.COMING_SOON
    if product.stock_quantity <= 0:
        return Availability.OUT_OF_STOCK
    return Availability.AVAILABLE


class UnknownCategoryError(ValueError):
    pass


class CatalogService:
    def __init__(self, repo: CatalogRepository) -> None:
        self._repo = repo
        self._categories = repo.categories()

    @property
    def categories(self) -> list[Category]:
        return list(self._categories)

    def sellable_counts(self) -> dict[int, int]:
        return self._repo.category_product_counts()

    def resolve_category(self, name: str) -> Category:
        key = normalize(name)
        for category in self._categories:
            if normalize(category.name) == key:
                return category
        raise UnknownCategoryError(f"Unknown category: {name!r}")

    def search(
        self,
        *,
        text: str | None = None,
        category: str | None = None,
        min_price: Decimal | None = None,
        max_price: Decimal | None = None,
        include_unavailable: bool = False,
        limit: int = 10,
        offset: int = 0,
    ) -> ProductPage:
        category_id = self.resolve_category(category).category_id if category else None
        return self._repo.search(
            text=text,
            category_id=category_id,
            min_price=min_price,
            max_price=max_price,
            sellable_only=not include_unavailable,
            limit=max(1, min(limit, MAX_PAGE_SIZE)),
            offset=max(0, offset),
        )

    def get(self, product_id: int) -> Product | None:
        return self._repo.get(product_id)

    def find_by_name(self, name: str) -> list[Product]:
        return self._repo.find_by_name(name)

    def alternatives(self, product: Product, limit: int = 3) -> list[Product]:
        return self._repo.alternatives(product, limit)

    def inactive_promotions(self, product_id: int) -> list[Promotion]:
        return self._repo.inactive_promotions(product_id)
