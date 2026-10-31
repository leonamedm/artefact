"""Text normalization shared by ingestion and queries, so both sides compare the same form."""

from __future__ import annotations

import re
import unicodedata


def normalize(text: str) -> str:
    """Lowercase, strip accents and collapse whitespace ("Violão  Nylon" -> "violao nylon")."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", stripped.casefold()).strip()


def compact(text: str) -> str:
    """Normalized text with only letters and digits, so "GD-20" and "GD20" match."""
    return re.sub(r"[^a-z0-9]", "", normalize(text))


def search_tokens(text: str) -> list[str]:
    return [token for token in (compact(part) for part in normalize(text).split()) if token]


def digits(text: str) -> str:
    return re.sub(r"\D", "", text)
