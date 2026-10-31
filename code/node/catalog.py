"""The tools a business agent can use, shared by every node.

Every company agent is the same agent object (`node/agent.py`); this catalog is what all of
them know about the actions on the agent web. Tools marked "planned" are outlined here so
the agents can already reason about them, but they are not implemented yet (negotiation
and payment are later steps of goals.md).
"""

AVAILABLE, PLANNED = "available", "planned"

TOOLS = {
    "get_availability": {
        "status": AVAILABLE,
        "endpoint": "POST /tools/get_availability",
        "description": "Rooms and prices for a date, from the hotel's facts.",
    },
    "get_policies": {
        "status": AVAILABLE,
        "endpoint": "POST /tools/get_policies",
        "description": "Location, quietness, pets, check-in and cancellation policies.",
    },
    "book": {
        "status": AVAILABLE,
        "endpoint": "POST /tools/book",
        "description": "Confirm a booking; needs the guest's signed approval for exactly the total.",
    },
    "make_offer": {
        "status": AVAILABLE,
        "endpoint": "sends POST {posting.offer_url}",
        "description": "Answer a marketplace posting with a signed offer (room, price, add-ons, conditions); prices come from the hotel's config.",
    },
    "counter_offer": {
        "status": PLANNED,
        "endpoint": "POST /tools/counter_offer",
        "description": "Answer a guest's counter-offer during negotiation, within the owner's limits.",
    },
    "pay": {
        "status": PLANNED,
        "endpoint": "POST /tools/pay",
        "description": "Take a payment under the guest's mandate.",
    },
}


def tools_for(names: list[str]) -> dict:
    """The catalog entries for the tools one agent uses, in the agent's order."""
    unknown = [name for name in names if name not in TOOLS]
    if unknown:
        raise ValueError(f"unknown tools in agent config: {unknown}")
    return {name: TOOLS[name] for name in names}
