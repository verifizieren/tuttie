"""Tests for the hotel cards (assistant/cards.py): pros and cons from signed facts only."""

from assistant.cards import MAX_CARDS, card_order, hotel_card

GUESTHOUSE_FACTS = {
    "quiet": True, "distance_to_basel_sbb_m": 1900, "profile": {"size": "small", "about": "Family-run"},
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


def test_a_fitting_small_hotel_gets_pros_for_every_need():
    card = hotel_card(item("guesthouse", 135), GUESTHOUSE_FACTS, NEEDS, 160, shortlisted=True)
    assert card["pros"][:4] == ["Within your budget", "Dogs welcome, free", "Quiet", "Late arrival arranged"]
    assert "Small independent business" in card["pros"] and "Free cancellation" in card["pros"]
    assert card["cons"] == ["24 min walk to Basel SBB"]


def test_a_hotel_that_misses_the_needs_shows_why():
    card = hotel_card(item("city", 180), CITY_FACTS, NEEDS, 160, shortlisted=False)
    assert card["cons"] == ["CHF 20 over your budget", "No dogs", "Not a quiet location", "No late check-in",
                            "Best rate is non-refundable"]
    assert card["pros"] == ["11 min walk to Basel SBB"]


def test_without_a_budget_the_price_is_neither_pro_nor_con():
    card = hotel_card(item("guesthouse", 135), GUESTHOUSE_FACTS, [], None, shortlisted=True)
    assert not any("budget" in text for text in card["pros"] + card["cons"])


def test_the_shortlist_comes_first_then_the_rest_by_price():
    offers = [item(f"h{i}", price) for i, price in enumerate([300, 120, 200, 150, 250, 180, 90])]
    shortlist = [offers[1], offers[3]]
    order = [o["node_id"] for o in card_order(offers, shortlist)]
    assert order[:2] == ["h1", "h3"] and order[2:] == ["h6", "h5", "h2"] and len(order) == MAX_CARDS
