"""Hotel cards for the wallet: what each offer means for this user, from signed facts only.

After the market's offers are in, Tuttie bargains with the hotels and shows up to MAX_CARDS of
them as cards with the agreed price; the user swipes right (like) or left (pass), and Tuttie
books the best liked deal. A card is built
in code from the hotel's signed offer and its signed policies (get_policies), compared with
the user's needs and private budget: nothing on it comes from an LLM, and the budget itself
is never shown to a hotel.

Each feature is `{key, ok, label}`: `key` names the wallet's icon (dog, kids, quiet, late,
station, cancel, breakfast, wifi, parking, small), `ok` paints it green or red. Features that
answer the user's needs come first.
"""

import re

MAX_CARDS = 5
PHOTO_FILE = re.compile(r"[A-Za-z0-9_-]+\.(?:jpg|jpeg|png|webp)")
MAX_FEATURES = 5
MAX_NAME_CHARS = 60    # a business's agent name: one short line
MAX_SIZE_CHARS = 20    # a profile's size ("small", "medium", "large")
MAX_ABOUT_CHARS = 500  # a profile's "about"
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
    if profile_of(facts).get("size") == "small":
        add("small", True, "Independent")
    return found


def clean_text(value, limit: int) -> str | None:
    """A business's text as one short line: strings only, control and format characters (newlines,
    RTL overrides) replaced by spaces, at most `limit` characters; None if nothing is left."""
    if not isinstance(value, str):
        return None
    text = " ".join("".join(c if c.isprintable() else " " for c in value).split())[:limit].strip()
    return text or None


def profile_of(data: dict) -> dict:
    """The profile in a business's signed data (agent card or get_policies), cleaned: only `size`
    and `about`, as short strings; {} if there is no profile dict."""
    profile = data.get("profile")
    if not isinstance(profile, dict):
        return {}
    return {"size": clean_text(profile.get("size"), MAX_SIZE_CHARS),
            "about": clean_text(profile.get("about"), MAX_ABOUT_CHARS)}


def own_photos(node_id: str, photos) -> list[str]:
    """Only the hotel's own photos served with the wallet: `hotels/<node_id>/<file>.jpg|jpeg|png|webp`
    (optionally with a leading "/"). Anything else (other hosts, another hotel's folder, "..",
    query strings) is dropped, so a verified hotel cannot track the user or borrow photos."""
    if not isinstance(photos, list):
        return []
    prefix = f"hotels/{node_id}/"
    return [p for p in photos if isinstance(p, str) and p.removeprefix("/").startswith(prefix)
            and PHOTO_FILE.fullmatch(p.removeprefix("/")[len(prefix):])]


def hotel_card(item: dict, facts: dict, requirements: list[str], budget_chf: float | None,
               shortlisted: bool, agreed_chf: float | None = None) -> dict:
    """One hotel's card: photos, rating, price, what is included and its features for this user.

    `item` is a checked offer from the market (assistant/marketplace.py), `facts` the payload of
    the hotel's signed get_policies, `shortlisted` whether it fits the private budget and
    `agreed_chf` the price in the hotel's signed agreement, if Tuttie's bargaining got one.
    """
    offer, needs = item["offer"], needs_text(requirements)
    wanted = {key for key, words in NEEDS.items() if any(w in needs for w in words)}
    # What the user asked for first, then the rest in a fixed order (sort is stable).
    ordered = sorted(features(facts), key=lambda f: f["key"] not in wanted)
    profile = profile_of(facts) or profile_of(item)  # both cleaned the same way
    price = offer["price_chf"]
    final = agreed_chf if agreed_chf is not None else price  # what the user would pay
    return {
        "node_id": item["node_id"],
        "name": item["name"],
        "trust_tier": item["trust_tier"],
        "size": profile.get("size"),
        "about": profile.get("about"),
        "agent": item.get("agent"),
        "rating": facts.get("rating"),
        "photos": own_photos(item["node_id"], facts.get("photos")),
        "offer_id": offer["offer_id"],
        "item": offer["item"],
        "price_chf": price,
        "agreed_chf": agreed_chf,
        # For the user's own wallet only (the hotel never sees the card or the budget).
        "over_budget_chf": round(final - budget_chf, 2) if budget_chf is not None and final > budget_chf else None,
        "includes": offer["includes"],
        "features": ordered[:MAX_FEATURES],
        "shortlisted": shortlisted,
    }


def card_order(offers: list[dict], shortlist: list[dict]) -> list[dict]:
    """The offers to show: the shortlist first (Tuttie's recommendation), then the rest by price."""
    picked = [o["offer"]["offer_id"] for o in shortlist]
    rest = sorted((o for o in offers if o["offer"]["offer_id"] not in picked), key=lambda o: o["offer"]["price_chf"])
    return (shortlist + rest)[:MAX_CARDS]
