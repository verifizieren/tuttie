# Marketplace (issues #8, #9, #10) — agent layer built (step 2)

The reverse marketplace: the user's agent posts a signed **request**, matching business
agents answer with signed **offers**, the user's agent picks. Built against the DRAFT
formats in `documentation/formats.md`; human layer (wallet) and negotiation come later.

| File | What |
| --- | --- |
| `messages.py` | All message formats as strict Pydantic models (Request, Offer, Counter, Posting, PostingCreated). Change formats here and in formats.md together. |
| `market.py` | The logic: verify postings (seals, signature, freshness, the user's delegation), wake matching businesses, verify and store offers, `shortlist`. No LLM. |
| `app.py` | HTTP service on port 4010 (`python -m marketplace.app`, started by `run.sh`). |
| `client.py` | Tuttie's side: `sign_request` with its own key, `post_request`. |

Flow:

1. Tuttie signs a `Request` and sends it to `POST /postings`. Refused unless Tuttie's seals
   hold, the envelope is fresh (≤ 300 s) and its delegation grants `post_requests`.
2. The market searches the registry for `category` + `tags`, skips broken businesses and
   wakes the others in parallel at `POST {endpoint}/agent/invoke` with
   `{"type": "posting.created", "posting": {...}}`. Their answer (`interested`, `next_tool`)
   is recorded per business; it is advisory, only a signed offer counts.
3. A business sends its signed `Offer` (from its `make_offer` tool) to the posting's
   `offer_url` = `POST /postings/{request_id}/offers`. Refused unless the business was
   invited, its seals still hold, the envelope is fresh and signed by it, and the offer is
   for this request and still valid. Prices are never changed by the market.
4. Tuttie reads `GET /postings/{id}` (everything) or `GET /postings/{id}/shortlist` (best
   five within budget: by price, grey last).

Refusals are `{"refused": true, "reason": "..."}` with 403 (trust), 404, 409 (duplicate),
410 (posting expired) or 422 (format). Postings are kept in memory until restart.

Tests: `code/tests/test_marketplace.py`.
