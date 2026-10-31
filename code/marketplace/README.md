# Marketplace (issues #8, #9, #10) — agent layer (step 2)

The reverse marketplace: the user's agent posts a signed **request**, matching business
agents answer with signed **offers**, the user's agent picks. Built against the DRAFT
formats in `documentation/formats.md`. The shortlist and the bargaining are not done here:
Tuttie builds its own shortlist (`assistant/marketplace.py`) and bargains through
`code/negotiation/`; the wallet shows the result.

| File | What |
| --- | --- |
| `messages.py` | All message formats as strict Pydantic models (Request, Offer, Counter, Posting, PostingCreated). Change formats here and in formats.md together. |
| `market.py` | The logic: verify postings (seals, signature, freshness, the user's delegation), wake matching verified businesses, verify and store offers. No LLM. |
| `app.py` | HTTP service on port 4010 (`python -m marketplace.app`, started by `run.sh`). |
| `client.py` | Tuttie's side: `sign_request` with its own key, `post_request`. |

Flow:

1. Tuttie signs a `Request` and sends it to `POST /postings`. Refused unless Tuttie's seals
   hold, the envelope is fresh (≤ 300 s) and its delegation grants `post_requests`.
2. The market searches the registry for `category` + `tags`, skips broken and untrusted
   (grey) businesses and wakes the verified ones whose agent card subscribes to
   `posting.created`, in parallel, at `POST {endpoint}/agent/invoke` with
   `{"type": "posting.created", "posting": {...}}`. Their answer (`interested`, `next_tool`)
   is recorded per business; it is advisory, only a signed offer counts.
3. A business sends its signed `Offer` (from its `make_offer` tool) to the posting's
   `offer_url` = `POST /postings/{request_id}/offers`. Refused unless the business was
   invited, its seals still hold, the envelope is fresh and signed by it, and the offer is
   for this request and still valid. Prices are never changed by the market.
4. Tuttie reads `GET /postings/{id}` (every accepted offer) and checks each offer again
   itself before it builds its shortlist with the private budget.

Refusals are `{"refused": true, "reason": "..."}` with 403 (trust), 404, 409 (duplicate),
410 (posting expired) or 422 (format). Postings are kept in memory until restart.

Tests: `code/tests/test_marketplace.py`.
