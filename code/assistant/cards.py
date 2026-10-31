"""Hotel cards for the wallet's picker: what each offer means for this user, from signed facts only.

After the market's offers are in, Tuttie shows up to MAX_CARDS hotels as cards the user can
swipe through and mark as favourites; Tuttie then negotiates only with the favourites. A card
is built in code from the hotel's signed offer and its signed policies (get_policies),
compared with the user's needs and private budget: nothing on it comes from an LLM, and the
budget itself is never shown to a hotel.
"""

MAX_CARDS = 5
WALK_M_PER_MIN = 80
NEAR_STATION_M = 1000
LATE_WORDS = ("late", "midnight", "after 22", "1am", "01:00", "night")


def needs_text(requirements: list[str]) -> str:
    return " ".join(requirements).lower()


def hotel_card(item: dict, facts: dict, requirements: list[str], budget_chf: float | None,
               shortlisted: bool) -> dict:
    """One hotel's card: price, what is included, pros and cons for this user's needs.

    `item` is a checked offer from the market (assistant/marketplace.py), `facts` the payload of
    the hotel's signed get_policies, `shortlisted` whether it fits the private budget.
    """
    offer, policies, needs = item["offer"], facts.get("policies") or {}, needs_text(requirements)
    pros, cons = [], []
    price = offer["price_chf"]
    if budget_chf is not None:
        if price <= budget_chf:
            pros.append("Within your budget")
        else:
            cons.append(f"CHF {price - budget_chf:g} over your budget")

    if policies.get("dogs_allowed"):
        fee = policies.get("dog_fee_chf_per_night") or 0
        pros.append("Dogs welcome, free" if not fee else f"Dogs welcome, CHF {fee:g} a night")
    elif "dog" in needs:
        cons.append("No dogs")

    if facts.get("quiet"):
        pros.append("Quiet")
    elif "quiet" in needs:
        cons.append("Not a quiet location")

    if any(word in needs for word in LATE_WORDS):
        late = (policies.get("late_arrival") or "").lower()
        if "24 hours" in late:
            pros.append("Reception open 24h")
        elif "closes" in late or "no check-in" in late:
            cons.append("No late check-in")
        elif late:
            pros.append("Late arrival arranged")

    distance = facts.get("distance_to_basel_sbb_m")
    if distance is not None:
        walk = f"{max(1, round(distance / WALK_M_PER_MIN))} min walk to Basel SBB"
        (pros if distance <= NEAR_STATION_M else cons).append(walk)

    cancellation = (policies.get("cancellation") or "").lower()
    if "non-refundable" in cancellation:
        cons.append("Best rate is non-refundable")
    elif "free" in cancellation:
        pros.append("Free cancellation")

    profile = facts.get("profile") or item.get("profile") or {}
    if profile.get("size") == "small":
        pros.append("Small independent business")

    return {
        "node_id": item["node_id"],
        "name": item["name"],
        "trust_tier": item["trust_tier"],
        "size": profile.get("size"),
        "about": profile.get("about"),
        "agent": item.get("agent"),
        "offer_id": offer["offer_id"],
        "item": offer["item"],
        "price_chf": price,
        "includes": offer["includes"],
        "pros": pros,
        "cons": cons,
        "shortlisted": shortlisted,
    }


def card_order(offers: list[dict], shortlist: list[dict]) -> list[dict]:
    """The offers to show: the shortlist first (Tuttie's recommendation), then the rest by price."""
    picked = [o["offer"]["offer_id"] for o in shortlist]
    rest = sorted((o for o in offers if o["offer"]["offer_id"] not in picked), key=lambda o: o["offer"]["price_chf"])
    return (shortlist + rest)[:MAX_CARDS]
