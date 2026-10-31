"""Extracts the policy manual into topic-keyed sections (see ADR-0003).

Headings are matched against the expected table of contents, in order. If the PDF changes and
a heading is not found, extraction fails instead of silently producing wrong sections.
"""

from __future__ import annotations

import re
from pathlib import Path

from pypdf import PdfReader

from emporio_agent.domain import PolicySection

MANUAL_VERSION = "2.1"

# (section number, exact heading, topic key, exposed to customers)
SECTIONS: tuple[tuple[int, str, str, bool], ...] = (
    (1, "Sobre a Empório da Música", "about", True),
    (2, "Horário de Funcionamento", "hours", True),
    (3, "Formas de Pagamento", "payment", True),
    (4, "Política de Trocas e Devoluções", "returns", True),
    (5, "Política de Frete e Entregas", "shipping", True),
    (6, "Promoções e Descontos", "promotions", True),
    (7, "Atendimento via WhatsApp", "service_guidelines", False),
    (8, "Garantia", "warranty", True),
    (9, "Privacidade e Proteção de Dados", "privacy", True),
    (10, "Disposições Finais", "final_provisions", False),
)

_PAGE_HEADER = "Empório da Música Manual de Políticas e Procedimentos"
_PAGE_FOOTER = re.compile(r"^Página \d+$")
_ZERO_WIDTH = re.compile(r"[​‌‍﻿]")
_COLUMN_GAP = re.compile(r"\s{3,}")


class PolicyExtractionError(ValueError):
    pass


def _clean_line(raw: str) -> str:
    line = _ZERO_WIDTH.sub("", raw).strip()
    line = re.sub(r"^•\s*", "- ", line)
    # Table columns come out separated by long runs of spaces; keep them readable as cells.
    return _COLUMN_GAP.sub(" | ", line)


def extract_sections(pdf_path: Path) -> list[PolicySection]:
    reader = PdfReader(pdf_path)
    lines: list[str] = []
    for page in reader.pages[1:]:  # page 1 is the cover
        for raw in page.extract_text(extraction_mode="layout").splitlines():
            line = _clean_line(raw)
            if line == _PAGE_HEADER or _PAGE_FOOTER.match(line):
                continue
            lines.append(line)

    sections: list[PolicySection] = []
    expected = iter(SECTIONS)
    current = next(expected)
    body: list[str] | None = None
    header: tuple[int, str, str, bool] | None = None

    def flush() -> None:
        if header is not None and body is not None:
            text = re.sub(r"\n{3,}", "\n\n", "\n".join(body)).strip()
            sections.append(PolicySection(header[0], header[1], header[2], header[3], text))

    for line in lines:
        if current is not None and line == f"{current[0]}. {current[1]}":
            flush()
            header, body = current, []
            current = next(expected, None)
            continue
        if body is not None:
            body.append(line)
    flush()

    if current is not None:
        raise PolicyExtractionError(f"Heading not found in manual: {current[0]}. {current[1]}")
    empty = [s.title for s in sections if not s.text]
    if empty:
        raise PolicyExtractionError(f"Empty sections in manual: {empty}")
    return sections
