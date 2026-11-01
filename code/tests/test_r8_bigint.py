"""Hunt 8: a JSON integer too big for a float (10**400) is not NaN/Infinity, so the r6 finite
checks let it through, and math.isfinite / f"{x:g}" raise OverflowError (not ValueError)."""
import pytest

from test_r6_trust import RHEIN, offer_item, run_check
from assistant.cards import features, hotel_card

BIG = 10 ** 400  # what json.loads("1" + "0" * 400) gives: an int, parse_float never sees it


def test_relayed_offer_with_a_huge_integer_price_is_dropped_not_raised():
    """check() must drop it as broken; today OverflowError escapes check -> poll -> find,
    so post_request fails and no cards show for that search."""
    assert run_check({}, offer_item(price=BIG))[0] is None


ITEM = {"node_id": RHEIN, "name": "Hotel Rheinblick", "trust_tier": "gold",
        "offer": {"offer_id": "o1", "item": "double", "price_chf": 140, "includes": [], "conditions": []}}


@pytest.mark.parametrize("facts", [
    {"rating": {"score": BIG, "reviews": 3}},
    {"distance_to_basel_sbb_m": BIG},
    {"policies": {"dogs_allowed": True, "dog_fee_chf_per_night": BIG}},
])
def test_signed_policies_with_a_huge_integer_do_not_break_the_cards(facts):
    """A sealed hotel's get_policies with a 400-digit integer must not crash hotel_card
    (post_request builds every card in one loop: one hotel would hide all cards)."""
    card = hotel_card(ITEM, facts, [], None, True)
    for feature in features(facts):
        assert isinstance(feature["label"], str)
    assert card["rating"] is None or 0 <= card["rating"]["score"] <= 5


def test_negotiation_price_check_survives_a_huge_integer():
    """negotiation.tuttie.is_price runs on every signed counter/agreement round (via MCP, whose
    json.loads hooks only catch floats): a 400-digit integer must be "not a price", not raise
    (an exception in one subagent fails asyncio.gather in negotiate_all -> no cards at all)."""
    from negotiation.tuttie import is_price
    assert is_price(BIG) is False
