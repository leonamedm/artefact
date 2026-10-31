"""Return, exchange and warranty eligibility (manual §4 and §8)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import StrEnum

from emporio_agent.domain import OrderStatus

REGRET_DAYS = 7  # §4.1, calendar days after receipt, online purchases only
PREFERENCE_DAYS = 7  # §4.3, counted from receipt (convention C8)
DEFECT_EXCHANGE_DAYS = 30  # §4.2, calendar days after purchase
LEGAL_WARRANTY_DAYS = 90  # §8.1, from receipt


class ReturnReason(StrEnum):
    REGRET = "regret"
    DEFECT = "defect"
    PREFERENCE = "preference"


class Outcome(StrEnum):
    ELIGIBLE = "eligible"
    EXPIRED = "expired"
    NOT_APPLICABLE = "not_applicable"
    NEEDS_RECEIVED_DATE = "needs_received_date"
    NEEDS_HUMAN = "needs_human"
    MANUFACTURER_WARRANTY = "manufacturer_warranty"


@dataclass(frozen=True)
class ReturnAssessment:
    reason: ReturnReason
    outcome: Outcome
    explanation: str
    deadline: date | None = None
    days_left: int | None = None
    conditions: tuple[str, ...] = field(default_factory=tuple)


_REGRET_CONDITIONS = (
    "Produto na embalagem original, sem sinais de uso, com todos os acessórios e manuais.",
    "Reembolso na mesma forma de pagamento em até 10 dias úteis.",
    "Frete de devolução por conta da loja.",
)
_PREFERENCE_CONDITIONS = (
    "Produto em perfeito estado e na embalagem original.",
    "Sujeito à disponibilidade do produto desejado.",
    "Diferenças de valor são cobradas ou reembolsadas conforme o caso.",
)
_DEFECT_CONDITIONS = (
    "Defeito de fabricação; danos por mau uso, quedas, umidade excessiva ou modificações "
    "não autorizadas não são cobertos.",
)


def _window(start: date, days: int, today: date) -> tuple[date, int]:
    deadline = start + timedelta(days=days)
    return deadline, (deadline - today).days


def assess_return(
    reason: ReturnReason,
    *,
    order_status: OrderStatus,
    purchase_date: date,
    received_date: date | None,
    today: date,
    online_purchase: bool = True,
    possibly_non_eligible: bool = False,
) -> ReturnAssessment:
    """possibly_non_eligible: customer reports customization/setup, a "final sale" clearance or a
    wind-instrument mouthpiece (§4.4). Data has no such flags, so a human confirms."""
    if received_date is not None:
        if received_date < purchase_date:
            raise ValueError("Received date cannot be before the purchase date")
        if received_date > today:
            raise ValueError("Received date cannot be in the future")

    if order_status is OrderStatus.CANCELLED:
        return ReturnAssessment(reason, Outcome.NOT_APPLICABLE, "Pedido cancelado.")
    if order_status is not OrderStatus.DELIVERED:
        return ReturnAssessment(
            reason,
            Outcome.NEEDS_HUMAN,
            "Pedido ainda não entregue; um atendente verifica a possibilidade de cancelamento.",
        )
    if possibly_non_eligible:
        return ReturnAssessment(
            reason,
            Outcome.NEEDS_HUMAN,
            "Item pode estar entre os não elegíveis (personalização/ajuste sob encomenda, "
            "liquidação com aviso de venda final ou boquilha); um atendente confirma.",
        )

    if reason is ReturnReason.DEFECT:
        deadline, days_left = _window(purchase_date, DEFECT_EXCHANGE_DAYS, today)
        if days_left >= 0:
            return ReturnAssessment(
                reason,
                Outcome.ELIGIBLE,
                f"Troca por defeito dentro de {DEFECT_EXCHANGE_DAYS} dias corridos da compra.",
                deadline,
                days_left,
                _DEFECT_CONDITIONS,
            )
        legal_deadline = (
            received_date + timedelta(days=LEGAL_WARRANTY_DAYS) if received_date else None
        )
        if legal_deadline is not None and today <= legal_deadline:
            explanation = (
                f"Prazo de troca na loja ({DEFECT_EXCHANGE_DAYS} dias) encerrado. Ainda na "
                f"garantia legal de {LEGAL_WARRANTY_DAYS} dias: a garantia é acionada com o "
                "fabricante e a loja pode intermediar o processo."
            )
        else:
            explanation = (
                f"Prazo de troca na loja ({DEFECT_EXCHANGE_DAYS} dias) encerrado. Garantia "
                "do fabricante conforme o certificado do produto (geralmente 6 meses a 2 anos); "
                "a loja pode intermediar."
            )
        return ReturnAssessment(
            reason,
            Outcome.MANUFACTURER_WARRANTY,
            explanation,
            legal_deadline,
            (legal_deadline - today).days if legal_deadline else None,
            _DEFECT_CONDITIONS,
        )

    if reason is ReturnReason.REGRET and not online_purchase:
        return ReturnAssessment(
            reason,
            Outcome.NOT_APPLICABLE,
            "Direito de arrependimento vale apenas para compras online.",
        )
    if received_date is None:
        return ReturnAssessment(
            reason,
            Outcome.NEEDS_RECEIVED_DATE,
            "O prazo conta a partir do recebimento; pergunte ao cliente a data em que recebeu.",
        )
    days = REGRET_DAYS if reason is ReturnReason.REGRET else PREFERENCE_DAYS
    conditions = _REGRET_CONDITIONS if reason is ReturnReason.REGRET else _PREFERENCE_CONDITIONS
    label = (
        "Devolução por arrependimento"
        if reason is ReturnReason.REGRET
        else ("Troca por preferência")
    )
    deadline, days_left = _window(received_date, days, today)
    if days_left >= 0:
        return ReturnAssessment(
            reason,
            Outcome.ELIGIBLE,
            f"{label} dentro de {days} dias corridos do recebimento.",
            deadline,
            days_left,
            conditions,
        )
    return ReturnAssessment(
        reason,
        Outcome.EXPIRED,
        f"{label}: prazo de {days} dias corridos após o recebimento encerrado em "
        f"{deadline.strftime('%d/%m/%Y')}.",
        deadline,
        days_left,
    )
