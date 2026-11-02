from __future__ import annotations

import json


def run(tools, tool_name, **arguments):
    return tools.execute(tool_name, json.dumps(arguments))


def test_schemas_are_valid_function_definitions(tools):
    for schema in tools.schemas():
        assert schema["type"] == "function"
        params = schema["function"]["parameters"]
        assert params["type"] == "object"
        # Gemini's OpenAI-compatible endpoint rejects some JSON-schema keywords.
        assert "additionalProperties" not in json.dumps(params)


def test_unknown_tool_and_bad_arguments_return_errors(tools):
    assert "error" in tools.execute("nope", "{}")
    assert "error" in tools.execute("get_product", "not json")
    assert "error" in run(tools, "search_products", max_price="abc")
    assert "error" in run(tools, "search_products", category="Pedais")


def test_numeric_strings_are_coerced(tools):
    result = run(tools, "search_products", category="Violões", max_price="1000")
    assert result["total_matches"] > 0


def test_partial_search_page_is_flagged(tools):
    # 12 guitars cost up to R$ 1.000 (real data); the default page holds 8.
    first = run(tools, "search_products", category="Violões", max_price=1000)
    assert (first["total_matches"], first["returned"]) == (12, 8)
    assert "4 more match" in first["more_results"] and "offset=8" in first["more_results"]
    rest = run(tools, "search_products", category="Violões", max_price=1000, offset=8)
    assert rest["returned"] == 4 and "more_results" not in rest


def test_get_product_by_name_formats_money(tools):
    result = run(tools, "get_product", name="Takamine GD20")
    assert result["price"] == "R$ 2.199,00"
    assert result["pix_price"] == "R$ 2.089,05"
    assert result["installments"]["max_interest_free"] == "12x de R$ 183,25"
    assert result["expired_promotions"]  # had an "Oferta Especial" that ended


def test_promotion_presented_with_original_and_percent(tools):
    result = run(tools, "get_product", product_id=94)
    assert result["promotion"] == {
        "name": "Desconto Exclusivo",
        "discount_percent": 8,
        "original_price": "R$ 5.999,00",
        "promotional_price": "R$ 5.519,08",
    }
    assert result["pix_discount_applies"] is False


def test_unavailable_products_have_no_price_but_alternatives(tools):
    result = run(tools, "get_product", product_id=136)
    assert "price" not in result
    assert result["alternatives"]
    assert "descontinuado" in result["availability"]


def test_quote_mixes_promo_and_pix_rules_and_shipping(tools):
    # Ohana CK-20 (20% promo: R$ 439,20) + Kala KA-15S (R$ 199,90, PIX R$ 189,91).
    result = run(
        tools,
        "quote_purchase",
        items=[{"product_id": 121}, {"product_id": 116}],
        city="Campo Grande",
    )
    assert result["subtotal"] == "R$ 639,10"
    assert result["pix_total"] == "R$ 629,11"
    assert result["shipping"]["fee"] == "R$ 0,00"


def test_quote_reports_insufficient_stock(tools):
    result = run(tools, "quote_purchase", items=[{"product_id": 93, "quantity": 5}])
    assert result["insufficient_stock"] == [
        {"product": "Martin D-28 Dreadnought Natural", "units_in_stock": 2}
    ]
    assert "subtotal" not in result


def test_lookup_orders_requires_identification(tools):
    assert "error" in run(tools, "lookup_orders", order_id=8)
    denied = run(tools, "lookup_orders", order_id=8, phone="(67) 99999-0000")
    assert denied["identified"] is False
    assert "orders" not in denied


def test_lookup_order_shows_tracking_and_delay(tools):
    result = run(tools, "lookup_orders", order_id=8, phone="(67) 99654-7821")
    order = result["orders"][0]
    assert result["customer_first_name"] == "Ana"
    assert order["tracking_code"] == "BRJL5544332BR"
    assert order["delayed"] is True
    assert order["payment_method"] == "Cartão de débito"


def test_return_check_needs_received_date(tools):
    result = run(
        tools, "check_return_eligibility", order_id=8, phone="(67) 99654-7821", reason="regret"
    )
    assert result["outcome"] == "needs_human"  # order 8 not delivered yet


def test_policy_and_store_info(tools):
    policy = run(tools, "get_policy", topic="returns")
    assert "seção 4" in policy["source"]
    info = run(tools, "get_store_info")
    assert info["whatsapp"] == "(67) 3321-4500"
    assert info["is_open_now"] is True  # Saturday 10:00


def test_handoff_is_recorded(tools, conversations):
    result = run(tools, "handoff_to_human", reason="complaint", summary="Instrumento com defeito")
    assert result["registered"] is True
    assert result["response_time"] == "Retorno em até 24 horas úteis."
