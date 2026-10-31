"""The business side's bargaining rules (negotiation/rules.py): pure functions, no I/O."""

import json
from pathlib import Path

import pytest

from negotiation.rules import CLOSE_CHF, Limits, decide, floor_total

NODES = Path(__file__).resolve().parent.parent / "data" / "nodes"
HOTELS = [json.loads(p.read_text()) for p in sorted(NODES.glob("*.json"))
          if json.loads(p.read_text())["facts"].get("negotiation")]
LIMITS = Limits(min_share=170 / 180, max_rounds=3)  # Rheinblick: double 180, floor 170
DOG = [{"item": "dog in the room", "price_chf": 15}]


def test_limits_from_facts_use_the_standard_room():
    facts = {"rooms": [{"room_type": "single", "price_chf": 95, "available": True},
                       {"room_type": "double", "price_chf": 135, "available": True}],
             "negotiation": {"floor_chf": 125, "max_rounds": 3}}
    assert Limits.from_facts(facts) == Limits(min_share=125 / 135, max_rounds=3)
    assert Limits.from_facts({"rooms": facts["rooms"]}) is None  # no limits: does not negotiate


@pytest.mark.parametrize("config", HOTELS, ids=lambda c: c["node_id"])
def test_every_hotels_floor_is_below_its_standard_room(config):
    limits = Limits.from_facts(config["facts"])
    assert 0 < limits.min_share < 1 and limits.max_rounds >= 1


def test_floor_discounts_the_room_but_never_the_add_ons():
    assert floor_total(180, [], DOG, LIMITS) == 170
    assert floor_total(195, ["dog in the room"], DOG, LIMITS) == 185  # 170 + 15
    assert floor_total(205, [], DOG, LIMITS) == 194  # same share for the dearer room, rounded up


def test_paying_the_hotels_price_is_an_agreement_at_that_price():
    decision = decide(200, 1, 180, False, 170, LIMITS)
    assert (decision.kind, decision.price_chf) == ("agreement", 180)


def test_hotel_meets_halfway_and_never_goes_below_its_floor():
    counter = decide(150, 1, 180, False, 170, LIMITS)
    assert (counter.kind, counter.price_chf, counter.final) == ("counter", 170, True)  # halfway 165 → floor
    counter = decide(170, 1, 180, False, 170, LIMITS)
    assert (counter.kind, counter.price_chf, counter.final) == ("counter", 175, False)


def test_close_or_last_round_counters_at_or_above_the_floor_are_accepted():
    assert decide(180 - CLOSE_CHF, 1, 180, False, 170, LIMITS).kind == "agreement"
    last = decide(171, 3, 178, False, 170, LIMITS)
    assert (last.kind, last.price_chf) == ("agreement", 171)


def test_last_round_below_the_floor_gets_a_final_counter_then_nothing_more():
    final = decide(160, 3, 175, False, 170, LIMITS)
    assert final.kind == "counter" and final.final and final.price_chf >= 170
    assert decide(165, 4, final.price_chf, True, 170, LIMITS).kind == "rejection"
    assert decide(final.price_chf, 4, final.price_chf, True, 170, LIMITS).kind == "agreement"  # accepting is fine
    assert decide(165, 4, 175, False, 170, LIMITS).kind == "rejection"  # beyond max_rounds


def test_no_limits_means_fixed_prices():
    assert decide(150, 1, 180, False, None, None).kind == "rejection"
    assert decide(180, 1, 180, False, None, None).kind == "agreement"


def test_no_sequence_of_counters_gets_below_the_floor():
    """Whatever the guest does, every price the hotel proposes or accepts stays >= the floor."""
    for start in range(1, 200, 7):
        previous, final = 195.0, False
        for round_ in range(1, 6):
            decision = decide(start + round_, round_, previous, final, 185, LIMITS)
            if decision.kind == "rejection":
                break
            assert decision.price_chf >= 185
            if decision.kind == "agreement":
                break
            assert decision.price_chf <= previous  # the hotel never goes back up
            previous, final = decision.price_chf, decision.final
