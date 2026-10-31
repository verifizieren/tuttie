"""Hotel cards for the wallet: what each offer means for this user, from signed facts only.

After the market's offers are in, Tuttie shows up to MAX_CARDS hotels as cards the user swipes
right (like) or left (pass); Tuttie then negotiates only with the liked ones. A card is built
in code from the hotel's signed offer and its signed policies (get_policies), compared with
the user's needs and private budget: nothing on it comes from an LLM, and the budget itself
is never shown to a hotel.

Each feature is `{key, ok, label}`: `key` names the wallet's icon (dog, kids, quiet, late,
station, cancel, breakfast, wifi, parking, small), `ok` paints it green or red. Features that
answer the user's needs come first.
"""

MAX_CARDS = 5
MAX_FEATURES = 7
WALK_M_PER_MIN = 80
NEAR_STATION_M = 1000
NEEDS = {  # feature key -> words in the user's requirements that make it matter most
    "dog": ("dog",), "kids": ("kid", "child", "family"), "quiet": ("quiet",),
    "late": ("late", "midnight", "after 22", "1am", "01:00", "night"), "station": ("station", "sbb"),
}


def needs_text(requirements: list[str]) -> str:
    return " ".join(requirements).lower()


def features(facts: dict) -> list[dict]:
    """Every feature the hotel's signed policies tell about, green (ok) or red."""
    policies, amenities = facts.get("policies") or {}, facts.get("amenities") or {}
    found = []

    def add(key, ok, label):
        found.append({"key": key, "ok": ok, "label": label})

    if "dogs_allowed" in policies:
        fee = policies.get("dog_fee_chf_per_night") or 0
        add("dog", bool(policies["dogs_allowed"]),
            ("Dogs free" if not fee else f"Dogs CHF {fee:g}") if policies["dogs_allowed"] else "No dogs")
    if "kids_beds" in amenities:
        add("kids", amenities["kids_beds"], "Kids' beds" if amenities["kids_beds"] else "No kids' beds")
    if "quiet" in facts:
        add("quiet", bool(facts["quiet"]), "Quiet" if facts["quiet"] else "Not quiet")
    late = (policies.get("late_arrival") or "").lower()
    if late:
        ok = not ("closes" in late or "no check-in" in late)
        add("late", ok, ("24h reception" if "24 hours" in late else "Late arrival") if ok else "No late check-in")
    distance = facts.get("distance_to_basel_sbb_m")
    if distance is not None:
        add("station", distance <= NEAR_STATION_M, f"{max(1, round(distance / WALK_M_PER_MIN))} min to SBB")
    cancellation = (policies.get("cancellation") or "").lower()
    if cancellation:
        add("cancel", "non-refundable" not in cancellation,
            "Non-refundable" if "non-refundable" in cancellation else "Free cancellation")
    for key, label in (("breakfast", "Breakfast"), ("wifi", "Wifi"), ("parking", "Parking")):
        if key in amenities:
            add(key, amenities[key], label if amenities[key] else f"No {label.lower()}")
    if (facts.get("profile") or {}).get("size") == "small":
        add("small", True, "Independent")
    return found


def hotel_card(item: dict, facts: dict, requirements: list[str], budget_chf: float | None,
               shortlisted: bool) -> dict:
    """One hotel's card: rating, price, what is included and its features for this user.

    `item` is a checked offer from the market (assistant/marketplace.py), `facts` the payload of
    the hotel's signed get_policies, `shortlisted` whether it fits the private budget.
    """
    offer, needs = item["offer"], needs_text(requirements)
    wanted = {key for key, words in NEEDS.items() if any(w in needs for w in words)}
    # What the user asked for first, then the rest in a fixed order (sort is stable).
    ordered = sorted(features(facts), key=lambda f: f["key"] not in wanted)
    profile = facts.get("profile") or item.get("profile") or {}
    price = offer["price_chf"]
    return {
        "node_id": item["node_id"],
        "name": item["name"],
        "trust_tier": item["trust_tier"],
        "size": profile.get("size"),
        "about": profile.get("about"),
        "agent": item.get("agent"),
        "rating": facts.get("rating"),
        "offer_id": offer["offer_id"],
        "item": offer["item"],
        "price_chf": price,
        "over_budget_chf": round(price - budget_chf, 2) if budget_chf is not None and price > budget_chf else None,
        "includes": offer["includes"],
        "features": ordered[:MAX_FEATURES],
        "shortlisted": shortlisted,
    }


def card_order(offers: list[dict], shortlist: list[dict]) -> list[dict]:
    """The offers to show: the shortlist first (Tuttie's recommendation), then the rest by price."""
    picked = [o["offer"]["offer_id"] for o in shortlist]
    rest = sorted((o for o in offers if o["offer"]["offer_id"] not in picked), key=lambda o: o["offer"]["price_chf"])
    return (shortlist + rest)[:MAX_CARDS]
