"""Data preparation pipeline: load -> check -> (optionally) write. Dry-run unless apply=True."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path

from emporio_agent.config import (
    CATALOG_DB,
    POLICIES_JSON,
    POLICY_PDF,
    PREPARE_REPORT,
    SOURCE_CSV,
)
from emporio_agent.ingest.build import build_catalog
from emporio_agent.ingest.checks import Finding, run_checks
from emporio_agent.ingest.policies import MANUAL_VERSION, extract_sections
from emporio_agent.ingest.sources import load_sources

TRANSFORMATIONS = (
    "prices and order totals: decimal BRL -> integer cents (exact arithmetic in SQL)",
    "products.specs: JSON string -> validated JSON",
    "derived products.name_compact / search_compact: accent-free alphanumeric search keys",
    "derived customers.phone_digits / email_norm: identification keys",
    "empty tracking_code / estimated_delivery / notes -> NULL",
    "policy manual: PDF -> topic-keyed sections (policies.json)",
    "no source value is corrected; anomalies are reported as findings",
)


@dataclass
class PrepareReport:
    applied: bool
    reference_date: str
    source_hashes: dict[str, str]
    row_counts: dict[str, int]
    policy_sections: list[str]
    findings: list[Finding]
    outputs: list[str] = field(default_factory=list)

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "error"]

    def to_json(self) -> str:
        data = asdict(self)
        data["transformations"] = list(TRANSFORMATIONS)
        return json.dumps(data, ensure_ascii=False, indent=2)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(data_dir: Path, var_dir: Path, *, apply: bool, reference_date: date) -> PrepareReport:
    source_files = [data_dir / name for name in SOURCE_CSV.values()] + [data_dir / POLICY_PDF]
    src = load_sources(data_dir)
    sections = extract_sections(data_dir / POLICY_PDF)
    report = PrepareReport(
        applied=False,
        reference_date=reference_date.isoformat(),
        source_hashes={p.name: _sha256(p) for p in source_files},
        row_counts={
            "categories": len(src.categories),
            "products": len(src.products),
            "promotions": len(src.promotions),
            "customers": len(src.customers),
            "orders": len(src.orders),
            "order_items": len(src.order_items),
        },
        policy_sections=[f"{s.number}. {s.title} -> {s.topic}" for s in sections],
        findings=run_checks(src, reference_date),
    )
    if not apply or report.errors:
        return report

    built_at = datetime.now().astimezone().isoformat(timespec="seconds")
    build_catalog(
        src,
        var_dir / CATALOG_DB,
        {
            "built_at": built_at,
            "manual_version": MANUAL_VERSION,
            **{f"sha256:{name}": digest for name, digest in report.source_hashes.items()},
        },
    )
    policies = {
        "manual_version": MANUAL_VERSION,
        "sections": [asdict(s) for s in sections],
    }
    (var_dir / POLICIES_JSON).write_text(
        json.dumps(policies, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    report.applied = True
    report.outputs = [str(var_dir / name) for name in (CATALOG_DB, POLICIES_JSON, PREPARE_REPORT)]
    (var_dir / PREPARE_REPORT).write_text(report.to_json(), encoding="utf-8")
    return report
