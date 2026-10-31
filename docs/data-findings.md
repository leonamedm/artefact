# Data and manual findings

Source files in `data/` are never edited. Every finding below is either enforced by a tested
rule or recorded as an assumption/convention. `tools/prepare_data.py` re-detects the data
findings on every run and logs them (`var/prepare_report.json`).

- **Cn** = convention: a choice made because the source is ambiguous or contradictory.
- **An** = assumption: information the data does not contain.
- **On** = open item: needs confirmation from the store.

## Products
| Finding | Handling | Test |
|---|---|---|
| Status: 62 `active`, 2 `discontinued` (113, 136), 1 `coming_soon` (130) | Only `active` with stock > 0 is sellable. | `test_catalog` |
| Discontinued 136 still has stock 13; coming-soon 130 has stock 2 | **C7** status wins over stock: not offered; discontinued → equivalents, coming soon → no date promised. Unavailable items carry no price. | `test_status_wins_over_stock`, `test_unavailable_products_have_no_price_but_alternatives` |
| Stock 0: 96 (active), 113 (discontinued) | "Temporarily unavailable" + sellable alternatives of the same category, closest price. | `test_alternatives_are_sellable_same_category` |
| Categories 6, 7, 8 (woodwinds, brass, orchestral strings) have no products, though the manual says the store sells them | Search returns nothing; the agent says none are in the current catalog. | `test_empty_categories_return_nothing` |

## Promotions
| Finding | Handling | Test |
|---|---|---|
| Only 4 of 25 active (products 127, 121, 90, 94); no validity dates | `is_active` is the source of truth. Expired promotions are listed as ended so the agent can say so. | `test_expired_promotions_are_never_applied` |
| Products with several (inactive) promotions (93, 96, 99) | Build fails if a product ever has more than one *active* promotion (no precedence rule exists). | `test_known_data_anomalies_are_reported` |
| Display rule (§6.2) | Tools return original price, % and promotional price together. | `test_promotion_presented_with_original_and_percent` |
| Not cumulative; PIX 5% not on promotional price (§6.2) | Enforced per item in pricing and cart quote. | `test_active_promotion_…`, `test_quote_mixes_promo_and_pix_rules_and_shipping` |
| Price filters ("up to R$ 1.000") | Use the effective (promotional) price. | `test_price_filter_uses_promotional_price` |

## Orders
| Finding | Handling | Test |
|---|---|---|
| 20 orders; 12 without `tracking_code` (all not yet dispatched or cancelled) | Tracking shown only for `shipped`/`delivered` (§5.3). | `test_tracking_only_after_dispatch`, `test_confirmed_order_has_no_tracking` |
| Order 8 `shipped`, ETA 2026-02-28 long passed | Flagged `delayed`; agent offers a hand-off. | `test_lookup_order_shows_tracking_and_delay` |
| Orders 9–16 `pending`/`confirmed` since Feb–Mar 2026 | Reported as-is; no invented explanation. Operational follow-up (**O5**). | — |
| Totals differ from items at current prices: order 3 (3,450 vs 3,498), order 20 (1,400 vs 1,488) | **A3** the recorded total is reported; never recomputed (prices may have changed). | `test_order_total_is_the_recorded_one` |
| Order 3 `delivered` contains `coming_soon` product 130 | Logged; no customer impact. | `test_known_data_anomalies_are_reported` |
| No purchase-channel field | **A1** orders in the system are online purchases (they have shipping data). | — |
| No received date | **A2** the agent asks the customer; ETA is never used as the receipt date. | `test_regret_requires_received_date_never_assumes_eta` |

## Customers (LGPD, §9)
Order data is returned only after identification: order id + the phone **or** e-mail on file,
or phone **and** e-mail to list all orders. Failures are indistinguishable, so the tool cannot
reveal which orders or customers exist. There is no "list customers" query anywhere.
Tests: `test_orders.py`, `test_lookup_orders_requires_identification`.

## Policy manual
| Finding | Handling (convention) | Test |
|---|---|---|
| §1.2 says "Telefone / WhatsApp (67) 3341-4444"; §7 (WhatsApp section) says (67) 3321-4500 | **C1** phone (67) 3341-4444 (cover and §1.2); WhatsApp (67) 3321-4500 (§7 is the dedicated channel section). | `test_contact_convention` |
| E-mail `contato@emporiodamusica.com.br` (cover) vs `contato@empóriodamusica.com.br` (§1.2) | **C2** ASCII version; an accented domain is almost certainly a typo. | `test_contact_convention` |
| §3 table: "parcela mínima R$ 100,00" for credit card; §3.1 defines 3 tiers | **C3** §3.1 (more specific) applies; R$ 100 is the 7–12x tier. | `test_installment_tiers` |
| §3.1 "até 3x sem valor mínimo (exceto abaixo de R$ 50,00)" is ambiguous | **C4** each installment in 2–3x must be ≥ R$ 50,00 (confirm: **O1**). | `test_installment_tiers` |
| Metropolitan region of Campo Grande not defined | **C5** only the city of Campo Grande is metro; other cities get carrier options and a "quote by CEP" — never an invented price (**O2**). | `test_shipping.py` |
| "Acima de R$ 500" free / "abaixo de R$ 500" R$ 35 — exactly R$ 500 undefined | **C6** strict: R$ 500,00 pays R$ 35. Threshold uses the goods value before payment-method discounts. | `test_metro_free_above_500_and_fee_otherwise` |
| Preference exchange "em até 7 dias" — start not stated | **C8** counted from receipt, like the regret right. | `test_preference_exchange_seven_days` |
| Defect exchange counts from *purchase* (30 d); regret and legal warranty from *receipt* | Implemented as written. | `test_returns.py` |
| §4.4 non-eligible items (custom setup, "final sale", mouthpieces) — no such flags in data | **A4** if the customer mentions one, a human confirms. | `test_possibly_non_eligible_item_goes_to_human` |
| "Closed on holidays" without a list | **A5** national + Mato Grosso do Sul holidays (`holidays` package); Campo Grande municipal holidays not covered (**O3**). | `test_store.py` |
| "Sugerir lojas parceiras" — no partner list | The agent does not name any store (**O4**). | prompt |
| §2: extended hours on special dates, announced on social media | Not in data; the agent says hours may be extended and to check announcements. | — |

## Open items for the store
- **O1** Confirm the 2–3x minimum installment interpretation (C4).
- **O2** List of metropolitan-region municipalities and a shipping-quote API for other cities.
- **O3** Municipal holidays of Campo Grande.
- **O4** Partner stores for accessories, if any.
- **O5** Orders open since Feb–Mar 2026 and order 8 past its ETA need operational follow-up.
