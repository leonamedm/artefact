from __future__ import annotations

import hashlib
from pathlib import Path

from emporio_agent.config import DATA_DIR
from emporio_agent.ingest.pipeline import prepare
from emporio_agent.ingest.policies import extract_sections
from emporio_agent.ingest.sources import load_sources
from tests.conftest import TODAY


def _codes(report, code):
    return [f.message for f in report.findings if f.code == code]


def _hash_dir(path: Path) -> dict[str, str]:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(path.iterdir())}


def test_dry_run_writes_nothing_and_never_touches_sources(tmp_path):
    before = _hash_dir(DATA_DIR)
    report = prepare(DATA_DIR, tmp_path, apply=False, reference_date=TODAY)
    assert not report.applied
    assert list(tmp_path.iterdir()) == []
    assert _hash_dir(DATA_DIR) == before


def test_apply_builds_outputs_without_changing_sources(tmp_path):
    before = _hash_dir(DATA_DIR)
    report = prepare(DATA_DIR, tmp_path, apply=True, reference_date=TODAY)
    assert report.applied
    assert {p.name for p in tmp_path.iterdir()} == {
        "emporio.db",
        "policies.json",
        "prepare_report.json",
    }
    assert _hash_dir(DATA_DIR) == before


def test_row_counts_match_source_files():
    src = load_sources(DATA_DIR)
    assert len(src.products) == 65
    assert len(src.orders) == 20
    assert len(src.promotions) == 25
    assert sum(p.is_active for p in src.promotions) == 4
    assert sum(o.tracking_code is None for o in src.orders) == 12


def test_known_data_anomalies_are_reported(tmp_path):
    report = prepare(DATA_DIR, tmp_path, apply=False, reference_date=TODAY)
    assert not report.errors
    assert any("product 136" in m for m in _codes(report, "DISCONTINUED_WITH_STOCK"))
    assert any("product 130" in m for m in _codes(report, "COMING_SOON_WITH_STOCK"))
    mismatches = _codes(report, "ORDER_TOTAL_MISMATCH")
    assert any(m.startswith("order 3:") for m in mismatches)
    assert any(m.startswith("order 20:") for m in mismatches)
    empty = " ".join(_codes(report, "CATEGORY_WITHOUT_PRODUCTS"))
    assert all(f"category {n} " in empty for n in (6, 7, 8))
    assert any("order 8" in m for m in _codes(report, "SHIPPED_PAST_ETA"))
    assert not _codes(report, "TRACKING_FORMAT")


def test_policy_manual_is_split_into_all_sections():
    sections = extract_sections(DATA_DIR / "políticas_da_loja.pdf")
    assert [s.number for s in sections] == list(range(1, 11))
    by_topic = {s.topic: s for s in sections}
    assert "09:00 às 18:00" in by_topic["hours"].text
    assert "7 (sete) dias corridos" in by_topic["returns"].text
    assert "R$ 500,00" in by_topic["shipping"].text
    assert not by_topic["service_guidelines"].customer_facing
    # Page headers/footers are stripped.
    assert all("Página" not in s.text for s in sections)
