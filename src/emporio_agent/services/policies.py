"""Policy manual sections by topic (ADR-0003)."""

from __future__ import annotations

import json
from pathlib import Path

from emporio_agent.domain import PolicySection
from emporio_agent.repositories.db import CatalogNotBuiltError


class PolicyService:
    def __init__(self, policies_path: Path) -> None:
        if not policies_path.exists():
            raise CatalogNotBuiltError(
                f"{policies_path} not found. Build it with: "
                "uv run python tools/prepare_data.py --apply"
            )
        data = json.loads(policies_path.read_text(encoding="utf-8"))
        self.manual_version: str = data["manual_version"]
        self._sections = {s["topic"]: PolicySection(**s) for s in data["sections"]}

    @property
    def customer_topics(self) -> list[str]:
        return [t for t, s in self._sections.items() if s.customer_facing]

    def get(self, topic: str) -> PolicySection:
        section = self._sections.get(topic)
        if section is None:
            raise KeyError(f"Unknown policy topic: {topic!r}")
        return section
