"""Tuttie's side of bargaining: one subagent per offer, all negotiating in parallel.

For every offer worth bargaining over, Tuttie spawns a subagent (assistant/subagents.py). The
subagent opens a session with that hotel's agent (both sides keep their own memory) and gets
only the context the hotel may see (`Context.share("negotiation")`). The bargaining moves are
made by Tuttie's code here, not by an LLM, and every move goes through the trust gate
(Toolbox.verified_post): the hotel's seals and the signature of every reply are checked.

The user's real budget limit is a *private* context item ("max_price_chf"). It is only
compared in this code, like a hotel's floor on the other side: it is never shared with a
subagent's context, never put in a prompt and never sent. Tuttie's counters stay at or below
it, and Tuttie walks away when a hotel's final price is above it.

Every counter is signed with Tuttie's own key; the hotel checks Tuttie's seals and the user's
delegation ("negotiate"). Prices only come from signed messages: the hotel's offer, its
counters and the final Agreement, which is what the user later approves on the phone.

Strategy (`next_price`): open at OPENING_DISCOUNT below the offer, then move TUTTIE_STEP of the
way toward the hotel's latest price; accept a hotel price within the limit once it is final or close.
A signed Agreement counts only at or below Tuttie's last counter and with the offer's terms
unchanged (`agreement_problem`); anything else ends the negotiation as "refused".
"""

import asyncio
import math
from dataclasses import dataclass, field

from nacl.signing import SigningKey

from aps import sign_envelope
from assistant.subagents import SubagentPool
from assistant.tools import Verified
from marketplace.messages import Counter, Offer
from negotiation.hotel import message
from negotiation.rules import CLOSE_CHF
from sessions import Context

BUDGET_LIMIT = "max_price_chf"  # private context item: the most the user will pay
# Strategy numbers; tune them for the demo with scripts/bargain_preview.py.
OPENING_DISCOUNT = 0.10  # first counter this far below the offer (tuned for the demo, see rules.HOTEL_STEP)
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


def opening_price(offer_price: float, limit: float) -> int:
    """Tuttie's first counter: a fair discount below the offer, never above the limit."""
    return min(math.floor(offer_price * (1 - OPENING_DISCOUNT)), math.floor(limit))


def next_price(own_last: float, hotel_price: float, limit: float) -> int:
    """Move TUTTIE_STEP of the way toward the hotel's price, never above the limit or the hotel's price."""
    step = math.ceil(own_last + (hotel_price - own_last) * TUTTIE_STEP)
    return min(step, math.floor(limit), math.floor(hotel_price))


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

        subagent = self.pool.spawn(node_id, f"negotiate {offer.offer_id}", context)
        outcome.subagent_id = subagent.id
        opened = await subagent.open()
        if subagent.remote_session is None:
            outcome.status, outcome.reason = "refused", opened.get("reason", "session refused")
            return outcome

        toolbox, memory = subagent.toolbox, subagent.memory
        own, last = opening_price(offer.price_chf, limit), None
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
        return await asyncio.gather(*(self.negotiate(o["node_id"], o["envelope"], context) for o in offers))


TERMS = ("request_id", "offer_id", "item", "room_type", "date", "rate", "includes", "conditions")


def agreement_problem(offer: Offer, reply: dict, ceiling: float) -> str:
    """Why a signed "agreement" is not what Tuttie agreed to, or "" if it is.

    A hotel only agrees to Tuttie's counter or to its own lower price, so the price must be at
    most `ceiling` (Tuttie's last counter, which never exceeds the private limit). The terms
    are the offer's, unchanged: only the price was negotiated.
    """
    price = reply.get("price_chf")
    if not isinstance(price, (int, float)) or price > ceiling:
        return "the agreement's price is above what Tuttie offered"
    changed = [key for key in TERMS if reply.get(key) != getattr(offer, key)]
    if changed:
        return f"the agreement does not match the offer ({', '.join(changed)})"
    return ""


def best(outcomes: list[Outcome]) -> Outcome | None:
    """The cheapest agreement, for the user to approve; None if no hotel agreed."""
    agreed = [o for o in outcomes if o.status == "agreed"]
    return min(agreed, key=lambda o: o.price_chf) if agreed else None


def summary(hotel: str, round_: int, own: float, reply: dict) -> str:
    """One timeline line per round, without any limit (Tuttie's or the hotel's)."""
    if reply.get("type") == "agreement":
        return f"{hotel}: agreed at CHF {reply['price_chf']:g} (round {round_})"
    if reply.get("type") == "counter":
        final = ", final" if reply.get("final") else ""
        return f"{hotel}: Tuttie CHF {own:g} → hotel CHF {reply['price_chf']:g}{final} (round {round_})"
    return f"{hotel}: {reply.get('reason', 'no agreement')} (round {round_})"
