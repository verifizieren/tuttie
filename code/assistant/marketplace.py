"""Tuttie's side of the marketplace: post a request, collect the signed offers, build the shortlist.

1. Tuttie posts a Request signed with its own key (marketplace/client.py). Only public needs
   go into it (date, guests, requirements, tags): the posting is seen by every matching
   business, so the user's real budget limit stays private and is only used for step 3.
2. The market wakes the matching agents, which send signed offers. Tuttie collects them and
   re-checks every one itself (the business's seals and the offer's signature): it trusts
   the market to relay, not to judge.
3. Tuttie builds the shortlist: verified businesses only, within the private budget, still
   valid, cheapest first (gold before blue at the same price), at most five.

Every step is emitted as a "marketplace" event (detail.phase = posted / offer / shortlist),
which the wallet shows as the human view of the marketplace.
"""

import asyncio
import os
from datetime import datetime, timedelta, timezone

import httpx

from aps import evaluate_record, load_signing_key, verify_envelope
from aps.envelope import parse_timestamp
from assistant.events import EventBus
from marketplace.client import new_request_id, post_request, sign_request
from marketplace.messages import Request

MARKETPLACE_URL = os.environ.get("MARKETPLACE_URL", f"http://localhost:{os.environ.get('MARKETPLACE_PORT', '4010')}")
TUTTIE_ID = os.environ.get("TUTTIE_ID", "ch.tuttie.alex-muster")
TRUSTED_TIERS = ("gold", "blue")
TIER_ORDER = {"gold": 0, "blue": 1}
SHORTLIST_SIZE = 5
POSTING_HOURS = 2      # how long a posting stays open
OFFER_WAIT_S = 45      # longest wait for the interested agents' offers (it stops as soon as all have offered)
POLL_S = 0.5


def shortlist(offers: list[dict], budget_chf: float | None, now: datetime, size: int = SHORTLIST_SIZE) -> list[dict]:
    """The best offers for the user: verified, within the private budget, still valid, cheapest first."""
    fitting = [
        o for o in offers
        if o["trust_tier"] in TRUSTED_TIERS
        and (budget_chf is None or o["offer"]["price_chf"] <= budget_chf)
        and parse_timestamp(o["offer"]["valid_until"]) > now
    ]
    return sorted(fitting, key=lambda o: (o["offer"]["price_chf"], TIER_ORDER[o["trust_tier"]]))[:size]


class MarketDesk:
    """Posts Tuttie's requests and turns the market's offers into a shortlist."""

    def __init__(self, http: httpx.AsyncClient, registry_url: str, bus: EventBus, authorities: dict,
                 market_url: str = MARKETPLACE_URL, agent_id: str = TUTTIE_ID,
                 offer_wait_s: float = OFFER_WAIT_S):
        self.http = http
        self.registry_url = registry_url.rstrip("/")
        self.bus = bus
        self.authorities = authorities
        self.market_url = market_url.rstrip("/")
        self.agent_id = agent_id
        self.offer_wait_s = offer_wait_s
        self.last_request: dict | None = None    # the last posted request (public part)
        self.last_shortlist: list[dict] = []     # its shortlisted offers, with their signed envelopes
        self.last_offers: list[dict] = []        # every checked offer for it (the user may pick any)
        self.last_budget: float | None = None    # the private budget it was shortlisted with

    async def find(self, date: str, requirements: list[str] | None = None, tags: list[str] | None = None,
                   category: str = "hotel", guests: int = 1, budget_chf: float | None = None) -> dict:
        """Post a request, wait for the offers and return the shortlist (the LLM tool post_request)."""
        now = datetime.now(timezone.utc)
        request = Request.model_validate({
            "request_id": new_request_id(), "category": category, "tags": tags or [],
            "constraints": {"date": date, "guests": guests, "requirements": requirements or []},  # no budget
            "expires_at": (now + timedelta(hours=POSTING_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        })
        envelope = sign_request(request, self.agent_id, load_signing_key(self.agent_id))
        try:
            posting = await post_request(self.http, self.market_url, envelope)
        except httpx.HTTPStatusError as error:
            reason = error.response.json().get("reason", str(error)) if error.response.content else str(error)
            self.bus.emit("marketplace", "broken", f"The market refused the request: {reason}")
            return {"error": f"market refused the request: {reason}"}

        public = request.model_dump(mode="json")
        interested = [n for n, i in posting["invited"].items() if i.get("status") == "interested"]
        # Only agents that announced make_offer will send one; waiting for the others only costs time.
        offering = [n for n in interested if posting["invited"][n].get("next_tool") == "make_offer"]
        self.bus.emit("marketplace", "verified",
                      f"Posted request: {category} on {date}; woke {len(posting['invited'])}, "
                      f"{len(interested)} interested",
                      detail={"phase": "posted", "request": public, "invited": posting["invited"],
                              "skipped": posting["skipped"]})

        offers = await self.collect(request.request_id, len(offering), posting["invited"])
        best = shortlist(offers, budget_chf, datetime.now(timezone.utc))
        self.last_request, self.last_shortlist = request.model_dump(mode="json"), best
        self.last_offers, self.last_budget = offers, budget_chf
        self.bus.emit("marketplace", "verified",
                      f"Shortlist: {len(best)} of {len(offers)} offers fit"
                      + (f" (budget CHF {budget_chf:g}, kept private)" if budget_chf else ""),
                      detail={"phase": "shortlist", "request_id": request.request_id,
                              "shortlist": [o["offer"]["offer_id"] for o in best]})
        return {
            "request_id": request.request_id,
            "posted": public,
            "woken": {n: {"name": i["name"], "status": i.get("status")} for n, i in posting["invited"].items()},
            "skipped": posting["skipped"],
            "offers_received": len(offers),
            "shortlist": [self.view(o) for o in best],
        }

    async def collect(self, request_id: str, expected: int, invited: dict) -> list[dict]:
        """Poll the posting until every interested agent has offered (or time runs out).

        `expected` counts hotels, so the wait ends once that many *different* hotels have sent
        an offer that checks out. A hotel keeps one offer: a newer one from the same hotel
        replaces its earlier one (its latest word), so one eager hotel can neither end the
        wait for the others nor fill the cards twice. Each offer is checked again by Tuttie
        and shown once on the timeline.
        """
        seen: set[str] = set()                  # offer ids already checked (valid or not)
        by_hotel: dict[str, dict] = {}          # node_id -> its latest offer that checked out
        deadline = asyncio.get_running_loop().time() + self.offer_wait_s
        while True:
            response = await self.http.get(f"{self.market_url}/postings/{request_id}")
            for item in response.json().get("offers", []):
                offer_id = item["offer"]["offer_id"]
                if offer_id in seen:
                    continue
                seen.add(offer_id)
                checked = await self.check(item, invited.get(item["node_id"], {}))
                if checked:
                    by_hotel[checked["node_id"]] = checked
            if len(by_hotel) >= expected or asyncio.get_running_loop().time() > deadline:
                return list(by_hotel.values())
            await asyncio.sleep(POLL_S)

    async def check(self, item: dict, invited: dict) -> dict | None:
        """Re-verify one offer: the business's seals from the registry and the offer's signature."""
        node_id = item["node_id"]
        record = (await self.http.get(f"{self.registry_url}/nodes/{node_id}")).json()
        verdict = evaluate_record(record, self.authorities)
        valid = (verdict["tier"] in TRUSTED_TIERS
                 and verify_envelope(item["envelope"], record["public_key"], expected_node_id=node_id)
                 and item["envelope"]["payload"] == item["offer"])
        offer = item["offer"]
        summary = f"{record['name']} offers {offer['item']} for CHF {offer['price_chf']:g}"
        if not valid:
            self.bus.emit("marketplace", "broken", f"{summary}: offer does not verify, ignored", record, verdict["seals"])
            return None
        event = self.bus.emit("marketplace", "verified", summary, record, verdict["seals"],
                              {"phase": "offer", "offer": offer, "agent": invited.get("agent"),
                               "profile": invited.get("profile")})
        return {**item, "trust_tier": verdict["tier"], "source_step": event["step"],
                "agent": invited.get("agent"), "profile": invited.get("profile")}

    @staticmethod
    def view(item: dict) -> dict:
        """What the LLM gets to know about one shortlisted offer."""
        offer = item["offer"]
        return {"node_id": item["node_id"], "name": item["name"], "trust_tier": item["trust_tier"],
                "size": (item.get("profile") or {}).get("size"), "agent": item.get("agent"),
                "offer_id": offer["offer_id"], "item": offer["item"], "price_chf": offer["price_chf"],
                "includes": offer["includes"], "conditions": offer["conditions"],
                "valid_until": offer["valid_until"], "source_step": item["source_step"]}
