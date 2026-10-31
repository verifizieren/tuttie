"""The business side's bargaining rules: pure functions, no I/O, no LLM.

A hotel's owner sets private limits in the node config, `facts.negotiation`:

    floor_chf   the lowest price the owner accepts for the standard room ("double", else the
                cheapest available room). Other rooms may be discounted by the same share,
                so a CHF 205 room of a hotel with a 180 → 170 floor goes down to 193.6 at most.
    max_rounds  how many counter-offers the hotel answers before its price is final.

Add-ons are never discounted: they are fixed prices from the config. The limits are only
compared here, in code. They never go into a prompt or a reply; what the guest sees is a
price the hotel proposes, which is never below the floor.

How the hotel answers a counter (`decide`):

    the guest pays at least the hotel's last price  → agreement at the hotel's last price
    the hotel's last price was final                → rejection (the final price still stands)
    more rounds than the owner allows               → rejection (the last price still stands)
    the guest is at or above the floor and close to
    the hotel's price, or this is the last round    → agreement at the guest's price
    otherwise                                       → counter HOTEL_STEP of the way toward
                                                      the guest (0.5 = halfway), never below
                                                      the floor; final in the last round or
                                                      once it hits the floor
"""

import math
from dataclasses import dataclass

STANDARD_ROOM = "double"
CLOSE_CHF = 2  # a gap this small is not worth another round
# How far the hotel moves toward the guest's counter each round (0.5 = halfway). Smaller steps
# mean more rounds before the floor; tune with scripts/bargain_preview.py.
HOTEL_STEP = 0.34  # tuned for the demo: Rheinblick 195 → 185 over three visible rounds


@dataclass(frozen=True)
class Limits:
    """The owner's private limits, normalised: the lowest share of a room price, and rounds."""

    min_share: float
    max_rounds: int

    @classmethod
    def from_facts(cls, facts: dict) -> "Limits | None":
        """Limits from a node's facts, or None if the business does not negotiate."""
        negotiation = facts.get("negotiation")
        rooms = [r for r in facts.get("rooms", []) if r.get("available")]
        if not negotiation or not rooms:
            return None
        standard = next((r for r in rooms if r["room_type"] == STANDARD_ROOM),
                        min(rooms, key=lambda r: r["price_chf"]))
        share = min(1.0, negotiation["floor_chf"] / standard["price_chf"])
        return cls(min_share=share, max_rounds=max(1, int(negotiation["max_rounds"])))


@dataclass(frozen=True)
class Decision:
    """What the hotel answers: "agreement", "counter" or "rejection", with a price or a reason."""

    kind: str
    price_chf: float | None = None
    final: bool = False
    reason: str = ""


def add_ons_total(includes: list[str], add_ons: list[dict]) -> float:
    """The fixed price of the add-ons an offer includes (matched by their item text)."""
    prices = {a["item"]: a["price_chf"] for a in add_ons}
    return sum(prices.get(item, 0) for item in includes)


def floor_total(offer_price: float, includes: list[str], add_ons: list[dict], limits: Limits) -> float:
    """The lowest total the hotel accepts for this offer: discounted room plus full add-ons."""
    extras = add_ons_total(includes, add_ons)
    room = offer_price - extras
    return math.ceil(room * limits.min_share) + extras


def decide(counter_price: float, counter_round: int, previous_price: float, previous_final: bool,
           lowest: float | None, limits: Limits | None) -> Decision:
    """The hotel's answer to one counter (see the module docstring for the rules).

    `previous_price` is the hotel's last price (the offer's price in round 1); `lowest` is
    floor_total for this offer, None when the business does not negotiate.
    """
    if counter_price >= previous_price:
        return Decision("agreement", previous_price)
    if limits is None or lowest is None:
        return Decision("rejection", reason="This business does not negotiate its prices; the offer stands.")
    if previous_final:
        return Decision("rejection", reason="The last price was final; it still stands.")
    if counter_round > limits.max_rounds:
        return Decision("rejection", reason="No more rounds; the last price still stands.")
    last_round = counter_round == limits.max_rounds
    if counter_price >= lowest and (previous_price - counter_price <= CLOSE_CHF or last_round):
        return Decision("agreement", counter_price)
    proposal = max(lowest, math.ceil(previous_price - (previous_price - counter_price) * HOTEL_STEP))
    proposal = min(proposal, previous_price)  # never go back up
    return Decision("counter", proposal, final=last_round or proposal <= lowest)
