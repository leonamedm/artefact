"""Tools exposed to the model. Each tool validates its arguments, calls a service and returns a
JSON-ready dict. Money and dates are pre-formatted so the model copies them instead of
computing or reformatting (ADR-0001)."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from emporio_agent.clock import Clock
from emporio_agent.domain import Order, OrderStatus, Product
from emporio_agent.money import format_brl
from emporio_agent.repositories.conversations import ConversationRepository
from emporio_agent.services.catalog import Availability, CatalogService, availability
from emporio_agent.services.orders import OrderService, is_delayed, tracking_visible
from emporio_agent.services.policies import PolicyService
from emporio_agent.services.pricing import quote_price
from emporio_agent.services.quote import quote_purchase
from emporio_agent.services.returns import ReturnReason, assess_return
from emporio_agent.services.store import CONTACT, OPENING_HOURS, WEEKDAY_NAMES, store_status

logger = logging.getLogger(__name__)

Handler = Callable[[dict[str, Any]], dict[str, Any]]


class ToolError(ValueError):
    """Expected failure explained to the model (bad argument, not found, not identified)."""


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Handler

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    def __init__(self, tools: list[Tool]) -> None:
        self._tools = {tool.name: tool for tool in tools}

    @property
    def names(self) -> list[str]:
        return list(self._tools)

    def schemas(self) -> list[dict[str, Any]]:
        return [tool.schema() for tool in self._tools.values()]

    def execute(self, name: str, raw_arguments: str) -> dict[str, Any]:
        tool = self._tools.get(name)
        if tool is None:
            return {"error": f"Unknown tool {name!r}"}
        try:
            arguments = json.loads(raw_arguments or "{}")
            if not isinstance(arguments, dict):
                raise ToolError("Arguments must be a JSON object")
            return tool.handler(_validate(arguments, tool.parameters))
        except (ToolError, json.JSONDecodeError) as exc:
            return {"error": str(exc)}
        except Exception:  # noqa: BLE001 - the conversation must survive a tool bug
            logger.exception("Tool %s failed", name)
            return {"error": "Internal error; offer to hand the customer over to an attendant."}


# --- argument validation ---------------------------------------------------------------------


def _coerce(value: Any, schema: dict[str, Any], field: str) -> Any:
    kind = schema.get("type")
    try:
        if kind == "integer":
            if isinstance(value, bool):
                raise ValueError
            if isinstance(value, float) and not value.is_integer():
                raise ValueError
            value = int(value)
        elif kind == "number":
            if isinstance(value, bool):
                raise ValueError
            value = Decimal(str(value))
        elif kind == "boolean":
            if not isinstance(value, bool):
                raise ValueError
        elif kind == "string":
            if not isinstance(value, str):
                raise ValueError
            value = value.strip()
        elif kind == "array":
            if not isinstance(value, list):
                raise ValueError
            value = [_coerce(item, schema["items"], f"{field}[]") for item in value]
        elif kind == "object":
            if not isinstance(value, dict):
                raise ValueError
            value = _validate(value, schema)
    except (ValueError, TypeError, InvalidOperation) as exc:
        raise ToolError(f"Argument {field!r} must be of type {kind}") from exc
    if "enum" in schema and value not in schema["enum"]:
        raise ToolError(f"Argument {field!r} must be one of {schema['enum']}")
    return value


def _validate(arguments: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    properties = schema.get("properties", {})
    result: dict[str, Any] = {}
    for key, value in arguments.items():
        if key in properties and value is not None and value != "":
            result[key] = _coerce(value, properties[key], key)
    missing = [key for key in schema.get("required", []) if key not in result]
    if missing:
        raise ToolError(f"Missing required argument(s): {', '.join(missing)}")
    return result


# --- presentation helpers --------------------------------------------------------------------

AVAILABILITY_LABEL = {
    Availability.AVAILABLE: "disponível",
    Availability.OUT_OF_STOCK: "temporariamente sem estoque",
    Availability.DISCONTINUED: "descontinuado (não faz mais parte do catálogo)",
    Availability.COMING_SOON: "em breve (ainda não disponível para venda)",
}

ORDER_STATUS_LABEL = {
    OrderStatus.PENDING: "pendente (aguardando confirmação)",
    OrderStatus.CONFIRMED: "confirmado (ainda não despachado)",
    OrderStatus.SHIPPED: "enviado",
    OrderStatus.DELIVERED: "entregue",
    OrderStatus.CANCELLED: "cancelado",
}

PAYMENT_LABEL = {"pix": "PIX", "boleto": "Boleto bancário", "debit": "Cartão de débito"}


def _payment_label(code: str) -> str:
    if code in PAYMENT_LABEL:
        return PAYMENT_LABEL[code]
    if code.startswith("credit_"):
        return f"Cartão de crédito em {code.removeprefix('credit_')}"
    return code


def _date(value: date | None) -> str | None:
    return value.strftime("%d/%m/%Y") if value else None


def _money(value: Decimal) -> str:
    return format_brl(value)


def product_summary(product: Product) -> dict[str, Any]:
    state = availability(product)
    view: dict[str, Any] = {
        "product_id": product.product_id,
        "name": product.name,
        "category": product.category_name,
        "availability": AVAILABILITY_LABEL[state],
    }
    if state is Availability.AVAILABLE:
        view["units_in_stock"] = product.stock_quantity
    # Discontinued and coming-soon items carry no price: nothing to sell, nothing to promise.
    if state in (Availability.AVAILABLE, Availability.OUT_OF_STOCK):
        quote = quote_price(product)
        view["price"] = _money(quote.list_price)
        if quote.promotion:
            view["promotion"] = {
                "name": quote.promotion.description,
                "discount_percent": quote.promotion.discount_percent,
                "original_price": _money(quote.list_price),
                "promotional_price": _money(quote.final_price),
            }
        view["pix_price"] = _money(quote.pix_price)
        view["pix_discount_applies"] = quote.pix_discount_applies
    return view


def _installments_view(options) -> dict[str, Any]:
    best = options[-1]
    return {
        "max_interest_free": f"{best.count}x de {_money(best.amount)}",
        "options": [f"{o.count}x de {_money(o.amount)}" for o in options],
    }


def _order_view(order: Order, today: date) -> dict[str, Any]:
    view: dict[str, Any] = {
        "order_id": order.order_id,
        # Named explicitly: the data has no dispatch date, only the purchase date.
        "order_placed_on": _date(order.order_date),
        "status": ORDER_STATUS_LABEL[order.status],
        "items": [f"{i.quantity}x {i.product_name}" for i in order.items],
        "total": _money(order.total),
        "payment_method": _payment_label(order.payment_method),
    }
    if tracking_visible(order):
        view["tracking_code"] = order.tracking_code
        view["tracking_note"] = "Consultar no site dos Correios ou da Jadlog."
    else:
        view["tracking_code"] = None
        view["tracking_note"] = "O código de rastreio só é gerado quando o pedido é despachado."
    if order.estimated_delivery:
        view["estimated_delivery"] = _date(order.estimated_delivery)
    if is_delayed(order, today):
        view["delayed"] = True
        view["delay_note"] = "Previsão de entrega já passou; ofereça encaminhar a um atendente."
    if order.notes:
        view["notes"] = order.notes
    return view


# --- tool factory ----------------------------------------------------------------------------


@dataclass
class ToolContext:
    catalog: CatalogService
    orders: OrderService
    policies: PolicyService
    conversations: ConversationRepository | None
    clock: Clock
    session_id: str | None = None


def build_tools(ctx: ToolContext) -> ToolRegistry:
    category_names = [c.name for c in ctx.catalog.categories]

    def search_products(args: dict[str, Any]) -> dict[str, Any]:
        page = ctx.catalog.search(
            text=args.get("query"),
            category=args.get("category"),
            min_price=args.get("min_price"),
            max_price=args.get("max_price"),
            include_unavailable=args.get("include_unavailable", False),
            limit=args.get("limit", 8),
            offset=args.get("offset", 0),
        )
        result: dict[str, Any] = {
            "total_matches": page.total,
            "returned": len(page.items),
            "products": [product_summary(p) for p in page.items],
            "note": "Price filters consider the promotional price when a promotion is active.",
        }
        if page.total == 0:
            result["note"] = (
                "No matching instruments in the current catalog. Say so; never invent products."
            )
        offset = int(args.get("offset", 0) or 0)
        remaining = page.total - offset - len(page.items)
        if remaining > 0:
            # Stated explicitly: small models present a truncated page as the full answer
            # (recorded example 01 listed 8 of 12 guitars as "the" options under R$ 1.000).
            result["more_results"] = (
                f"Showing {len(page.items)} of {page.total}; {remaining} more match. Tell the "
                f"customer this is a partial list and offer the rest (call again with "
                f"offset={offset + len(page.items)}) or a narrower search."
            )
        return result

    def get_product(args: dict[str, Any]) -> dict[str, Any]:
        if "product_id" in args:
            product = ctx.catalog.get(args["product_id"])
            candidates = [product] if product else []
        elif "name" in args:
            candidates = ctx.catalog.find_by_name(args["name"])
        else:
            raise ToolError("Provide product_id or name")
        if not candidates:
            return {"found": False, "note": "Product not in the catalog. Never guess a price."}
        if len(candidates) > 1:
            return {
                "found": False,
                "ambiguous": True,
                "candidates": [product_summary(p) for p in candidates],
                "note": "Several products match; ask the customer which one.",
            }
        product = candidates[0]
        view = product_summary(product)
        view.update(description=product.description, specs=product.specs)
        state = availability(product)
        if state is Availability.AVAILABLE:
            view["installments"] = _installments_view(quote_purchase([(product, 1)]).installments)
        else:
            view["alternatives"] = [product_summary(p) for p in ctx.catalog.alternatives(product)]
        expired = ctx.catalog.inactive_promotions(product.product_id)
        if expired:
            view["expired_promotions"] = [
                f"{p.description} ({p.discount_percent}%) — encerrada, não vale mais"
                for p in expired
            ]
        return view

    def quote(args: dict[str, Any]) -> dict[str, Any]:
        items: list[tuple[Product, int]] = []
        for entry in args["items"]:
            product = ctx.catalog.get(entry["product_id"])
            if product is None:
                raise ToolError(f"Unknown product_id {entry['product_id']}")
            items.append((product, entry.get("quantity", 1)))
        q = quote_purchase(items, args.get("city"))
        result: dict[str, Any] = {
            "lines": [
                {
                    "product": line.product.name,
                    "quantity": line.quantity,
                    "unit_price": _money(line.price.final_price),
                    **(
                        {
                            "promotion": f"{line.price.promotion.description} "
                            f"(-{line.price.promotion.discount_percent}%), "
                            f"de {_money(line.price.list_price)} por "
                            f"{_money(line.price.final_price)}"
                        }
                        if line.price.promotion
                        else {}
                    ),
                    "line_total": _money(line.line_total),
                    "pix_discount_applies": line.price.pix_discount_applies,
                }
                for line in q.lines
            ],
            "unavailable": [
                {"product": p.name, "availability": AVAILABILITY_LABEL[s]} for p, s in q.unavailable
            ],
            "insufficient_stock": [
                {"product": p.name, "units_in_stock": n} for p, n in q.insufficient_stock
            ],
        }
        if q.lines:
            result.update(
                subtotal=_money(q.subtotal),
                pix_total=_money(q.pix_total),
                pix_rule="PIX 5% off only on items without an active promotion (not cumulative).",
                card_installments=_installments_view(q.installments),
                combined_payment_allowed=q.combined_payment_allowed,
            )
        if q.shipping:
            s = q.shipping
            result["shipping"] = {
                "city": s.city,
                "metropolitan_region": s.metro,
                "fee": (_money(s.fee) if s.fee is not None else None),
                "delivery_estimate": s.delivery_estimate,
                "carrier_options": [f"{name}: {eta}" for name, eta in s.carrier_options],
                "notes": list(s.notes),
            }
        elif q.lines:
            result["shipping"] = "Ask the customer's city to quote shipping."
        return result

    def lookup_orders(args: dict[str, Any]) -> dict[str, Any]:
        today = ctx.clock.now().date()
        email, phone = args.get("email"), args.get("phone")
        if "order_id" in args:
            if not (email or phone):
                raise ToolError("Ask the customer for the e-mail or phone used in the purchase")
            found = ctx.orders.find_order(args["order_id"], email=email, phone=phone)
            if found is None:
                return _not_identified()
            order, customer = found
            return {
                "identified": True,
                "customer_first_name": customer.name.split()[0],
                "orders": [_order_view(order, today)],
            }
        if email and phone:
            found_all = ctx.orders.find_customer_orders(email=email, phone=phone)
            if found_all is None:
                return _not_identified()
            customer, orders = found_all
            return {
                "identified": True,
                "customer_first_name": customer.name.split()[0],
                "orders": [_order_view(o, today) for o in orders],
            }
        raise ToolError("Provide order_id plus email or phone, or both email and phone")

    def check_return(args: dict[str, Any]) -> dict[str, Any]:
        if not (args.get("email") or args.get("phone")):
            raise ToolError("Ask the customer for the e-mail or phone used in the purchase")
        found = ctx.orders.find_order(
            args["order_id"], email=args.get("email"), phone=args.get("phone")
        )
        if found is None:
            return _not_identified()
        order, _ = found
        received = None
        if "received_date" in args:
            try:
                received = date.fromisoformat(args["received_date"])
            except ValueError as exc:
                raise ToolError("received_date must be YYYY-MM-DD") from exc

        def assess(reason: ReturnReason):
            return assess_return(
                reason,
                order_status=order.status,
                purchase_date=order.order_date,
                received_date=received,
                today=ctx.clock.now().date(),
                # Assumption A1: orders in the system are online purchases.
                online_purchase=True,
                possibly_non_eligible=args.get("possibly_non_eligible", False),
            )

        try:
            assessment = assess(ReturnReason(args["reason"]))
            # Customers often follow a return question with "and if it has a defect?". Returning
            # this order's defect/warranty status up front keeps that answer computed by code
            # instead of the model generalizing from the policy text.
            defect = (
                assess(ReturnReason.DEFECT) if assessment.reason != ReturnReason.DEFECT else None
            )
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
        result: dict[str, Any] = {
            "order_id": order.order_id,
            "order_status": ORDER_STATUS_LABEL[order.status],
            "purchase_date": _date(order.order_date),
            "received_date": _date(received),
            "reason": assessment.reason.value,
            "outcome": assessment.outcome.value,
            "explanation": assessment.explanation,
            "deadline": _date(assessment.deadline),
            "days_left": assessment.days_left,
            "conditions": list(assessment.conditions),
            "next_step": (
                "If eligible or needs_human, offer to register a hand-off so an attendant "
                "starts the process."
            ),
        }
        if defect is not None:
            result["if_defect"] = {
                "outcome": defect.outcome.value,
                "explanation": defect.explanation,
                "deadline": _date(defect.deadline),
                "days_left": defect.days_left,
            }
        return result

    def get_policy(args: dict[str, Any]) -> dict[str, Any]:
        section = ctx.policies.get(args["topic"])
        return {
            "source": f"Manual de Políticas v{ctx.policies.manual_version}, seção {section.number}",
            "title": section.title,
            "text": section.text,
            "note": "For contact details use get_store_info (the manual has inconsistent ones).",
        }

    def get_store_info(_: dict[str, Any]) -> dict[str, Any]:
        status = store_status(ctx.clock.now())
        hours = {
            WEEKDAY_NAMES[day]: f"{start:%H:%M} às {end:%H:%M}"
            for day, (start, end) in OPENING_HOURS.items()
        }
        hours["domingo e feriados"] = "fechado"
        return {
            "name": CONTACT.name,
            "address": CONTACT.address,
            "phone": CONTACT.phone,
            "whatsapp": CONTACT.whatsapp,
            "email": CONTACT.email,
            "opening_hours": hours,
            "now": f"{status.now:%d/%m/%Y %H:%M} ({WEEKDAY_NAMES[status.now.weekday()]})",
            "is_open_now": status.is_open,
            "closed_reason": status.closed_reason,
            "next_opening": (
                status.next_opening.strftime("%d/%m/%Y às %H:%M") + " "
                f"({WEEKDAY_NAMES[status.next_opening.weekday()]})"
                if status.next_opening
                else None
            ),
            "special_dates": (
                "Horário pode ser estendido em datas especiais; avisos nas redes sociais."
            ),
        }

    def handoff(args: dict[str, Any]) -> dict[str, Any]:
        now = ctx.clock.now()
        ticket = None
        if ctx.conversations is not None:
            ticket = ctx.conversations.record_handoff(
                ctx.session_id, args["reason"], args["summary"], now
            )
        status = store_status(now)
        result: dict[str, Any] = {
            "registered": ticket is not None,
            "ticket": ticket,
            "whatsapp": CONTACT.whatsapp,
            "store_open_now": status.is_open,
        }
        if args["reason"] == "complaint":
            result["response_time"] = "Retorno em até 24 horas úteis."
        if not status.is_open and status.next_opening:
            result["team_back_at"] = status.next_opening.strftime("%d/%m/%Y às %H:%M")
        return result

    identity = {
        "order_id": {"type": "integer", "description": "Order number given by the customer."},
        "email": {"type": "string", "description": "E-mail given by the customer."},
        "phone": {"type": "string", "description": "Phone with area code given by the customer."},
    }

    return ToolRegistry(
        [
            Tool(
                "search_products",
                "Search the instrument catalog. Use for any question about which instruments "
                "exist, price ranges or recommendations. Returns only items available for sale "
                "unless include_unavailable is true. Use 'category' for the instrument type "
                "and 'query' for brand, model or features (e.g. 'yamaha', 'nylon', 'eletrico').",
                {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Brand, model or feature words.",
                        },
                        "category": {"type": "string", "enum": category_names},
                        "min_price": {"type": "number", "description": "Minimum price in BRL."},
                        "max_price": {"type": "number", "description": "Maximum price in BRL."},
                        "include_unavailable": {"type": "boolean"},
                        "limit": {"type": "integer", "description": "Max results (default 8)."},
                        "offset": {"type": "integer", "description": "For the next page."},
                    },
                },
                search_products,
            ),
            Tool(
                "get_product",
                "Get one product's current price, promotion, PIX price, installments, stock and "
                "specs. Call it before stating any price or availability. For unavailable items "
                "it returns alternatives. Lists expired promotions so you can say they ended.",
                {
                    "type": "object",
                    "properties": {
                        "product_id": {"type": "integer"},
                        "name": {
                            "type": "string",
                            "description": "Product name, e.g. Takamine GD20.",
                        },
                    },
                },
                get_product,
            ),
            Tool(
                "quote_purchase",
                "Totals for one or more products: subtotal, PIX total, card installments, whether "
                "payment methods can be combined, and shipping when the city is known.",
                {
                    "type": "object",
                    "properties": {
                        "items": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "product_id": {"type": "integer"},
                                    "quantity": {"type": "integer"},
                                },
                                "required": ["product_id"],
                            },
                        },
                        "city": {"type": "string", "description": "Delivery city."},
                    },
                    "required": ["items"],
                },
                quote,
            ),
            Tool(
                "lookup_orders",
                "Order status, items, total and tracking. Requires identification: order_id plus "
                "the customer's e-mail or phone, or e-mail plus phone to list all their orders. "
                "Never call it with data the customer did not give.",
                {"type": "object", "properties": identity},
                lookup_orders,
            ),
            Tool(
                "check_return_eligibility",
                "Apply the return/exchange/warranty rules to an order. reason: 'regret' (changed "
                "mind), 'defect' (manufacturing defect) or 'preference' (swap color/model). "
                "Ask the customer the date they received the product for regret/preference.",
                {
                    "type": "object",
                    "properties": {
                        **identity,
                        "reason": {"type": "string", "enum": [r.value for r in ReturnReason]},
                        "received_date": {
                            "type": "string",
                            "description": "YYYY-MM-DD. Only a date the customer explicitly "
                            "stated in this conversation; never assume or fill it in.",
                        },
                        "possibly_non_eligible": {
                            "type": "boolean",
                            "description": "True if the customer mentions customization/setup, a "
                            "'final sale' clearance or a mouthpiece.",
                        },
                    },
                    "required": ["order_id", "reason"],
                },
                check_return,
            ),
            Tool(
                "get_policy",
                "Official store policy text by topic: about (company, what the store sells), "
                "hours, payment, returns, shipping, promotions, warranty, privacy.",
                {
                    "type": "object",
                    "properties": {
                        "topic": {"type": "string", "enum": ctx.policies.customer_topics}
                    },
                    "required": ["topic"],
                },
                get_policy,
            ),
            Tool(
                "get_store_info",
                "Address, phone, WhatsApp, e-mail, opening hours and whether the store is open "
                "now.",
                {"type": "object", "properties": {}},
                get_store_info,
            ),
            Tool(
                "handoff_to_human",
                "Register a hand-off to a human attendant: complaints, missing information, order "
                "problems, return processes or when the customer asks for a person.",
                {
                    "type": "object",
                    "properties": {
                        "reason": {
                            "type": "string",
                            "enum": [
                                "complaint",
                                "order_issue",
                                "return_request",
                                "missing_information",
                                "customer_request",
                            ],
                        },
                        "summary": {"type": "string", "description": "One-line case summary."},
                    },
                    "required": ["reason", "summary"],
                },
                handoff,
            ),
        ]
    )


def _not_identified() -> dict[str, Any]:
    return {
        "identified": False,
        "note": "Order not found or the data does not match. Ask the customer to check the "
        "order number and the e-mail/phone used in the purchase. Reveal nothing else.",
    }
