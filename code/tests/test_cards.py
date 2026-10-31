"""Tests for the hotel cards (assistant/cards.py): features from signed facts only."""

from assistant.cards import MAX_CARDS, card_order, hotel_card

GUESTHOUSE_FACTS = {
    "quiet": True, "distance_to_basel_sbb_m": 1900, "profile": {"size": "small"}, "rating": {"score": 4.8, "reviews": 64},
    "amenities": {"breakfast": True, "wifi": True, "parking": False, "kids_beds": False},
    "policies": {"dogs_allowed": True, "dog_fee_chf_per_night": 0,
                 "late_arrival": "Arrivals until 02:00 are fine.", "cancellation": "Free cancellation until 48h before."},
}
CITY_FACTS = {
    "quiet": False, "distance_to_basel_sbb_m": 900, "profile": {"size": "medium"},
    "policies": {"dogs_allowed": False, "late_arrival": "Reception closes at 23:00; no check-in after that.",
                 "cancellation": "Best rate is non-refundable."},
}
NEEDS = ["quiet", "dog", "arrival after midnight"]


def item(node_id: str, price: float) -> dict:
    return {"node_id": node_id, "name": node_id, "trust_tier": "gold", "agent": "Anna",
            "offer": {"offer_id": f"of-{node_id}", "item": "double room", "price_chf": price, "includes": []}}


def shown(card: dict) -> list[tuple[str, bool, str]]:
    return [(f["key"], f["ok"], f["label"]) for f in card["features"]]


def test_the_users_needs_come_first_then_the_rest():
    card = hotel_card(item("guesthouse", 135), GUESTHOUSE_FACTS, NEEDS, 160, shortlisted=True)
    assert shown(card)[:3] == [("dog", True, "Dogs free"), ("quiet", True, "Quiet"), ("late", True, "Late arrival")]
    assert ("kids", False, "No kids' beds") in shown(card) and len(card["features"]) == 5
    assert card["rating"] == {"score": 4.8, "reviews": 64} and card["over_budget_chf"] is None


def test_a_hotel_that_misses_the_needs_shows_them_in_red():
    card = hotel_card(item("city", 180), CITY_FACTS, NEEDS, 160, shortlisted=False)
    assert shown(card)[:3] == [("dog", False, "No dogs"), ("quiet", False, "Not quiet"), ("late", False, "No late check-in")]
    assert ("cancel", False, "Non-refundable") in shown(card) and ("station", True, "11 min to SBB") in shown(card)
    assert card["over_budget_chf"] == 20


def test_an_agreed_price_within_the_budget_is_not_over_it():
    card = hotel_card(item("city", 180), CITY_FACTS, NEEDS, 160, shortlisted=False, agreed_chf=155)
    assert card["over_budget_chf"] is None
    assert hotel_card(item("city", 180), CITY_FACTS, NEEDS, 160, False, agreed_chf=170)["over_budget_chf"] == 10


def test_without_a_budget_nothing_is_over_budget():
    assert hotel_card(item("guesthouse", 135), GUESTHOUSE_FACTS, [], None, shortlisted=True)["over_budget_chf"] is None


def test_the_shortlist_comes_first_then_the_rest_by_price():
    offers = [item(f"h{i}", price) for i, price in enumerate([300, 120, 200, 150, 250, 180, 90])]
    shortlist = [offers[1], offers[3]]
    order = [o["node_id"] for o in card_order(offers, shortlist)]
    assert order[:2] == ["h1", "h3"] and order[2:] == ["h6", "h5", "h2"] and len(order) == MAX_CARDS
