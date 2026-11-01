"""Tuttie's side of bargaining: one subagent per offer, all negotiating in parallel.

For every offer worth bargaining over, Tuttie spawns a subagent (assistant/subagents.py). The
subagent opens a session with that hotel's agent (both sides keep their own memory) and gets
only the context the hotel may see (`Context.share("negotiation")`). The bargaining moves are
made by Tuttie's code here, not by an LLM, and every move goes through the trust gate
(Toolbox.verified_post): the hotel's seals and the signature of every reply are checked.

The user's real budget limit is a *private* context item ("max_price_chf"). It is only
compared in this code, like a hotel's floor on the other side: it is never shared with a
subagent's context, never put in a prompt and never sent. Tuttie's counters stay below it, and
Tuttie walks away when a hotel's final price is above it.

No counter price is computed from the limit (bug #18: capping at the limit sent the budget
itself, e.g. CHF 160, to every hotel far above it). A counter comes only from the offer and the
hotel's prices; the limit only decides whether Tuttie sends it (`opening_price`, `next_price`).
So a hotel can never read the budget off Tuttie's counters, it only learns what any walk-away
tells: the budget is below a price Tuttie did not offer.

Every counter is signed with Tuttie's own key; the hotel checks Tuttie's seals and the user's
delegation ("negotiate"). Prices only come from signed messages: the hotel's offer, its
counters and the final Agreement, which is what the user later approves on the phone.

Strategy: open at OPENING_DISCOUNT below the offer (DEEP_OPENING_DISCOUNT when that is not below
the limit; no counter at all when neither is), then move TUTTIE_STEP of the way toward the
hotel's latest price, or hold the last counter when that step would not stay below the limit;
accept a hotel price within the limit once it is final or close.
A signed Agreement counts only at or below Tuttie's last counter and with the offer's terms
unchanged (`agreement_problem`); anything else ends the negotiation as "refused".
"""

import asyncio
import math
from dataclasses import dataclass, field

from nacl.signing import SigningKey
from pydantic import ValidationError

from aps import sign_envelope
from assistant.subagents import SubagentPool
from assistant.tools import Verified
from marketplace.messages import Agreement, Counter, Offer
from negotiation.hotel import message
from negotiation.rules import CLOSE_CHF
from sessions import Context

BUDGET_LIMIT = "max_price_chf"  # private context item: the most the user will pay
# Strategy numbers; tune them for the demo with scripts/bargain_preview.py.
OPENING_DISCOUNT = 0.10  # first counter this far below the offer (tuned for the demo, see rules.HOTEL_STEP)
DEEP_OPENING_DISCOUNT = 0.20  # used instead when the usual opening is not below the private limit
TUTTIE_STEP = 0.5  # how far Tuttie moves toward the hotel's price each round (0.5 = halfway)
MAX_ROUNDS = 6  # Tuttie's own safety limit, whatever the hotel allows


@dataclass
class Outcome:
    """How one negotiation ended. `agreement` is the hotel's signed Agreement envelope."""

    node_id: str
    offer_id: str
    status: str  # "agreed", "walked_away", "rejected" (hotel ended it) or "refused" (did not verify)
    offer_price_chf: float
    price_chf: float | None = None
    rounds: int = 0
    agreement: dict | None = None
    reason: str = ""
    subagent_id: str = ""
    history: list[dict] = field(default_factory=list)  # (own price, hotel answer) per round


def opening_price(offer_price: float, limit: float) -> int | None:
    """Tuttie's first counter, from the offer alone; None when no opening stays below the limit.

    The limit only picks between two discounts of the offer (or none): a counter is never
    capped at the limit, so it never equals or reveals the private budget.
    """
    for discount in (OPENING_DISCOUNT, DEEP_OPENING_DISCOUNT):
        price = math.floor(offer_price * (1 - discount))
        if price < limit:
            return price
    return None


def next_price(own_last: float, hotel_price: float, limit: float) -> int:
    """Move TUTTIE_STEP of the way toward the hotel's price, never above the hotel's price.

    If that step is not below the private limit, Tuttie holds its last counter instead of
    moving to the limit (which would send the budget itself).
    """
    step = min(math.ceil(own_last + (hotel_price - own_last) * TUTTIE_STEP), math.floor(hotel_price))
    return step if step < limit else own_last


class TuttieNegotiator:
    """Runs Tuttie's negotiations through its subagents."""

    def __init__(self, pool: SubagentPool, agent_id: str, agent_key: SigningKey):
        self.pool = pool
        self.agent_id = agent_id
        self.agent_key = agent_key

    def counter(self, offer: Offer, round_: int, price: float) -> dict:
        """A Counter about `offer`, signed with Tuttie's own key."""
        body = Counter(offer_id=offer.offer_id, round=round_, price_chf=price,
                       includes=offer.includes, conditions=offer.conditions)
        return sign_envelope(self.agent_id, body.model_dump(), self.agent_key)

    async def negotiate(self, node_id: str, offer_envelope: dict, context: Context) -> Outcome:
        """Bargain over one signed offer until agreement, rejection or walking away."""
        offer = Offer.model_validate(message(offer_envelope["payload"]))
        limit = float(context.items[BUDGET_LIMIT].value) if BUDGET_LIMIT in context.items else offer.price_chf
        outcome = Outcome(node_id, offer.offer_id, "walked_away", offer.price_chf)
        own = opening_price(offer.price_chf, limit)
        if own is None:  # walk away before talking: no counter could stay below the budget
            outcome.reason = "the offer is far above the budget"
            return outcome

        subagent = self.pool.spawn(node_id, f"negotiate {offer.offer_id}", context)
        outcome.subagent_id = subagent.id
        try:
            return await self.bargain(subagent, node_id, offer, offer_envelope, limit, own, outcome)
        finally:
            await self.pool.close(subagent)  # free the hotel's session slot, whatever happened

    async def bargain(self, subagent, node_id: str, offer: Offer, offer_envelope: dict, limit: float,
                      own: float, outcome: Outcome) -> Outcome:
        """The rounds of one negotiation, through `subagent` (negotiate opens and closes it)."""
        last = None
        opened = await subagent.open()
        if subagent.remote_session is None:
            outcome.status, outcome.reason = "refused", opened.get("reason", "session refused")
            return outcome

        toolbox, memory = subagent.toolbox, subagent.memory
        for round_ in range(1, MAX_ROUNDS + 1):
            body = {"counter": self.counter(offer, round_, own), "offer": offer_envelope, "last": last}
            memory.add("self", "counter", {"round": round_, "price_chf": own})
            result = await toolbox.verified_post(node_id, "/tools/counter_offer", body, "a2a", "counter-offer")
            outcome.rounds = round_
            if not isinstance(result, Verified):
                memory.add("system", "refused", result)
                outcome.status, outcome.reason = "refused", result.get("reason", "")
                return outcome
            reply = result.payload
            memory.add("peer", reply.get("type", reply.get("status", "reply")), message(reply))
            outcome.history.append({"round": round_, "own_chf": own, "hotel": message(reply)})
            toolbox.emit_verified("a2a", summary(result.record["name"], round_, own, reply), result)

            if reply.get("status") == "refused":
                outcome.status, outcome.reason = "refused", reply.get("reason", "")
                return outcome
            if reply.get("type") == "agreement":
                problem = agreement_problem(offer, reply, min(limit, own))
                if problem:
                    outcome.status, outcome.reason = "refused", problem
                    return outcome
                outcome.status, outcome.price_chf, outcome.agreement = "agreed", reply["price_chf"], result.envelope
                return outcome
            if reply.get("type") == "rejection":
                outcome.status, outcome.reason = "rejected", reply.get("reason", "")
                return outcome

            if not is_price(reply.get("price_chf")):
                outcome.status, outcome.reason = "refused", "the hotel's counter has no valid price"
                return outcome
            hotel_price, last = reply["price_chf"], result.envelope
            if hotel_price <= limit and (reply.get("final") or hotel_price - own <= CLOSE_CHF):
                own = hotel_price  # accept: the next counter matches the hotel's price
            elif reply.get("final"):
                outcome.reason = "the hotel's final price is above the budget"
                return outcome
            else:
                own = next_price(own, hotel_price, limit)
        outcome.reason = "no agreement within Tuttie's rounds"
        return outcome

    async def negotiate_all(self, offers: list[dict], context: Context) -> list[Outcome]:
        """Negotiate every offer at once, one subagent each.

        `offers` are accepted marketplace offers ({"node_id", "envelope", ...}); the outcomes
        come back in the same order.
        """
        return await asyncio.gather(*(self.isolated(o, context) for o in offers))

    async def isolated(self, offer: dict, context: Context) -> Outcome:
        """negotiate for one offer; an unexpected error ends only this hotel's talk, as refused."""
        try:
            return await self.negotiate(offer["node_id"], offer["envelope"], context)
        except Exception as error:  # noqa: BLE001 - one hotel's failure must not drop the others
            payload = (offer.get("envelope") or {}).get("payload") or {}
            price = payload.get("price_chf") if is_price(payload.get("price_chf")) else 0
            return Outcome(str(offer.get("node_id", "")), str(payload.get("offer_id", "")), "refused", price,
                           reason=f"negotiation failed: {type(error).__name__}")


TERMS = ("request_id", "offer_id", "item", "room_type", "date", "rate", "includes", "conditions")


def agreement_problem(offer: Offer, reply: dict, ceiling: float) -> str:
    """Why a signed "agreement" is not what Tuttie agreed to, or "" if it is.

    A hotel only agrees to Tuttie's counter or to its own lower price, so the price must be at
    most `ceiling` (Tuttie's last counter, which never exceeds the private limit). The terms
    are the offer's, unchanged: only the price was negotiated.
    """
    price = reply.get("price_chf")
    if not is_price(price):
        return "the agreement's price is not a valid price"
    if price > ceiling:
        return "the agreement's price is above what Tuttie offered"
    try:
        Agreement.model_validate(message(reply))
    except (ValidationError, TypeError):
        return "not a valid agreement"
    changed = [key for key in TERMS if reply.get(key) != getattr(offer, key)]
    if changed:
        return f"the agreement does not match the offer ({', '.join(changed)})"
    return ""


def is_price(value) -> bool:
    """A real price in CHF: a finite number above zero (a bool is not a number here)."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value) and value > 0
    except OverflowError:  # an int too big for a float
        return False


def best(outcomes: list[Outcome]) -> Outcome | None:
    """The cheapest agreement, for the user to approve; None if no hotel agreed."""
    agreed = [o for o in outcomes if o.status == "agreed"]
    return min(agreed, key=lambda o: o.price_chf) if agreed else None


def summary(hotel: str, round_: int, own: float, reply: dict) -> str:
    """One timeline line per round, without any limit (Tuttie's or the hotel's)."""
    price = f"{reply['price_chf']:g}" if is_price(reply.get("price_chf")) else "?"
    if reply.get("type") == "agreement":
        return f"{hotel}: agreed at CHF {price} (round {round_})"
    if reply.get("type") == "counter":
        final = ", final" if reply.get("final") else ""
        return f"{hotel}: Tuttie CHF {own:g} → hotel CHF {price}{final} (round {round_})"
    return f"{hotel}: {reply.get('reason', 'no agreement')} (round {round_})"
