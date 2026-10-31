"""Paths and runtime settings. Everything configurable comes from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Original files exactly as delivered by the store. Never written to.
DATA_DIR = Path(os.environ.get("EMPORIO_DATA_DIR", PROJECT_ROOT / "data"))
# Generated artefacts (catalog database, extracted policies, conversations). Git-ignored.
VAR_DIR = Path(os.environ.get("EMPORIO_VAR_DIR", PROJECT_ROOT / "var"))

SOURCE_CSV = {
    "categories": "desafio_tecnico_ai_eng - categories.csv",
    "products": "desafio_tecnico_ai_eng - products.csv",
    "promotions": "desafio_tecnico_ai_eng - promotions.csv",
    "customers": "desafio_tecnico_ai_eng - customers.csv",
    "orders": "desafio_tecnico_ai_eng - orders.csv",
    "order_items": "desafio_tecnico_ai_eng - order_items.csv",
}
POLICY_PDF = "políticas_da_loja.pdf"

CATALOG_DB = "emporio.db"
POLICIES_JSON = "policies.json"
PREPARE_REPORT = "prepare_report.json"
CONVERSATIONS_DB = "conversations.db"

# Google Gemini's OpenAI-compatible endpoint: free tier, no credit card (see ADR-0002).
DEFAULT_LLM_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
DEFAULT_LLM_MODEL = "gemini-flash-latest"


@dataclass(frozen=True)
class LLMSettings:
    base_url: str
    api_key: str
    model: str
    temperature: float

    @classmethod
    def from_env(cls) -> LLMSettings:
        api_key = os.environ.get("LLM_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "LLM_API_KEY is not set. Copy .env.example to .env and fill it in "
                "(for a local Ollama server any non-empty value works)."
            )
        return cls(
            base_url=os.environ.get("LLM_BASE_URL", DEFAULT_LLM_BASE_URL).strip(),
            api_key=api_key,
            model=os.environ.get("LLM_MODEL", DEFAULT_LLM_MODEL).strip(),
            # Low temperature: answers must stick to tool results, not be creative.
            temperature=float(os.environ.get("LLM_TEMPERATURE", "0.2")),
        )
