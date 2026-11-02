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


# Seconds per model request. Hosted APIs answer in seconds; small local models on modest
# hardware can take a minute or more per tool round, so Ollama entries usually raise it.
DEFAULT_LLM_TIMEOUT = 60.0


@dataclass(frozen=True)
class LLMSettings:
    """One provider endpoint. Loaded from `.env` by `emporio_agent.providers` (ADR-0007)."""

    base_url: str
    api_key: str
    model: str
    temperature: float
    timeout: float = DEFAULT_LLM_TIMEOUT
    name: str = "default"
