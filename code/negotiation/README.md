# Negotiation — bargaining between agents (step 4, issue #10)

Tuttie and the hotels bargain over a signed offer from the marketplace. Prices are decided by
code on both sides, never by an LLM, and each side's limit stays private: the hotel's floor
(`facts.negotiation`) never leaves the node, the user's budget (`max_price_chf`) never leaves
Tuttie. Owner: dev member 2. Formats: `documentation/formats.md` ("Counter-offer",
"Agreement", "Rejection", "`counter_offer` tool").

| File | What |
| --- | --- |
| `rules.py` | The hotel's rules as pure functions: floor for the double room (same share for other rooms), add-ons never discounted, move `HOTEL_STEP` toward the guest, `final` in the last round or at the floor. |
| `hotel.py` | The stateless `counter_offer` tool: checks Tuttie's seals, signature, freshness and `negotiate` delegation, and the hotel's own signed offer and last counter. Served over HTTP (`counter_offer_router`) and MCP (`counter_offer_mcp_tool`), same code. |
| `tuttie.py` | `TuttieNegotiator`: one subagent per offer, all in parallel; opens `OPENING_DISCOUNT` below, moves `TUTTIE_STEP` toward the hotel, walks away above the budget; `best()` picks the cheapest agreement. |
| `agreement.py` | `AgreementRedeemer`: at booking, the hotel accepts only its own signed, unexpired agreement, once (used by the action gate). |

The pitch story (pinned in `tests/test_negotiation_flow.py`): Gästehaus am Rhein, CHF 135,
budget 160 → Tuttie 121 → 131 → 126 → 130 → agreed at **CHF 128**. Tune the numbers with
`scripts/bargain_preview.py` (no LLM), and tell the pitch team if the story changes.

Tests: `test_negotiation_rules.py`, `test_counter_offer.py`, `test_counter_offer_mcp.py`,
`test_negotiation_flow.py`, `test_negotiation_edges.py`, `test_agreement.py` (100 % coverage).
