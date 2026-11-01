"""Tools the LLM may call, each wrapped in the APS trust gate.

Before the LLM sees any result, the node's registry record is checked against
data/authorities.json and every response envelope is verified with the node's
key. Anything that fails is replaced by {"rejected": true, "reason": ...} and
shown in red on the timeline. The node is never even contacted when its seals
are broken.

A business's tools are called over MCP (assistant/mcp_client.py). Reading tools are open;
`book` goes out as a call signed with Tuttie's key and carrying the user's delegation
(aps/call.py), so the hotel knows who asks and that the call is not replayed.

Results carry "source_step", the timeline step that proves them, so every fact Tuttie uses
can be traced to the signed reply behind it (Tuttie's answers do not cite them).
"""

import inspect
import json
import math
import re
from dataclasses import dataclass
from datetime import date as Date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from aps import agent_key, evaluate_record, load_signing_key, verify_envelope
from aps.approval import booking_terms, payment_charge, plain_term
from aps.call import sign_call
from aps.mandate import AUTO_PAY_LIMIT_CHF, may_auto_pay
from aps.delegation import verify_delegation
from aps.envelope import is_fresh
from aps.keys import load_public_key
from assistant.approvals import ApprovalBook
from assistant.cards import card_order, hotel_card
from assistant.context import UserContext
from assistant.marketplace import MarketDesk
from assistant.mcp_client import McpCallFailed, McpLink
from sessions import Context
from assistant.events import EventBus

AUTHORITIES_PATH = Path(__file__).resolve().parent.parent / "data" / "authorities.json"
TOOL_NAME = re.compile(r"^[a-z_]{1,40}$")
NODE_ID = re.compile(r"^[a-z0-9.-]{1,80}$")
# Tools the assistant may call freely; book needs the user's approval first.
READ_TOOLS = {"get_availability", "get_policies", "get_forecast", "get_connections"}  # the last two: services/server.py
# Node replies must be this fresh, so an old signed reply (e.g. an outdated price) cannot be replayed.
MAX_REPLY_AGE_S = 300
MAX_GUESTS = 10  # what a business node takes (node/server.py)
SWISS_TIME = ZoneInfo("Europe/Zurich")


def swiss_today() -> Date:
    """Today's date in Switzerland, where the user lives (the same day today_note gives the LLM)."""
    return datetime.now(SWISS_TIME).date()


def stay_error(day, guests, nights) -> str | None:
    """Why a hotel request cannot be posted as asked, or None. The error tells the LLM to ask the
    user, so a past night, a wrong party size or a longer stay is never silently changed."""
    try:
        night = Date.fromisoformat(day) if isinstance(day, str) and len(day) == 10 else None
    except ValueError:
        night = None
    if night is None:
        return "date must be YYYY-MM-DD"
    today = swiss_today()
    if night < today:
        return (f"{day} is in the past (today is {today}). Do not post it: tell the user and ask "
                "which night they mean.")
    if isinstance(guests, bool) or not isinstance(guests, int) or not 1 <= guests <= MAX_GUESTS:
        return f"guests must be a whole number from 1 to {MAX_GUESTS}: ask the user how many people are coming"
    if isinstance(nights, bool) or not isinstance(nights, int) or nights < 1:
        return "nights must be a whole number of at least 1"
    if nights > 1:
        return (f"Hotels on the agent web take one night per booking so far, so {nights} nights cannot be "
                "booked here. Tell the user honestly and ask whether to book just the first night "
                f"({day}); if yes, post again with nights=1.")
    return None


def function(name: str, description: str, properties: dict, required: list[str] | None = None) -> dict:
    """A tool definition in the chat-completions schema (llm.py converts it)."""
    parameters = {"type": "object", "properties": properties, "required": required or []}
    return {"type": "function", "function": {"name": name, "description": description, "parameters": parameters}}


SCHEMAS = [
    function("current_deals", "Read the current verified offers and signed negotiated agreements. "
             "Use before answering questions about prices or whether a negotiation succeeded.", {}),
    function("swipe_card", "Like or pass the hotel card currently visible in the wallet. "
             "Use for spoken like/pass commands, not a request to book a named hotel. "
             "The wallet handles the selection; never call book in the same turn.",
             {"verdict": {"type": "string", "enum": ["like", "pass"]}}, ["verdict"]),
    function(
        "recall_context",
        "Read what you know about the user: calendar, mail, messages and preferences, each item classed "
        "public, negotiation or private. Call it first whenever the user wants to find or book something.",
        {},
    ),
    function(
        "post_request",
        "Post the user's request on the marketplace: matching verified businesses are woken and "
        "send signed offers; returns the shortlist (verified, within budget, cheapest first). "
        "Use this first when the user looks for a hotel.",
        {
            "date": {"type": "string",
                     "description": "YYYY-MM-DD, the check-in night: the one the user names, else the calendar's"},
            "guests": {"type": "integer",
                       "description": "how many people: the number the user names, else the calendar's, else 1"},
            "nights": {"type": "integer",
                       "description": "how many nights: the number the user names, else the calendar's, else 1"},
            "requirements": {"type": "array", "items": {"type": "string"},
                             "description": "public needs, e.g. [\"quiet\", \"dog\", \"arrival around 01:00\"]"},
            # Only the city: an area tag left out every hotel outside it (the train to Basel SBB once
            # hid the guesthouse in Kleinbasel). A wish for an area goes into requirements instead.
            "tags": {"type": "array", "items": {"type": "string", "enum": ["basel"]},
                     "description": "the city; areas and everything else (near the station, quiet, dog, ...) "
                                    "go into requirements"},
            "budget_chf": {"type": "number",
                           "description": "the user's price limit. PRIVATE: it is never posted, only used for the shortlist"},
        },
        ["date"],
    ),
    function(
        "negotiate",
        "Bargain at once (one subagent each) with the user's favourite hotels, or without favourites "
        "with the whole shortlist, and return the best signed agreement.",
        {"budget_chf": {"type": "number",
                        "description": "the user's price limit. PRIVATE: only compared by Tuttie's code, never sent"},
         "node_ids": {"type": "array", "items": {"type": "string"},
                      "description": "the user's favourites (node ids); omit to negotiate with the shortlist"}},
    ),
    function(
        "search_registry",
        "Find nodes on the agent web by tags (all must match) and/or a capability. "
        "Results are seal-checked: use only 'verified', never 'rejected'.",
        {
            "tags": {"type": "array", "items": {"type": "string"},
                     "description": "Known tags: hotel, basel-sbb, dog-friendly, quiet, family, legal, consumer-law, switzerland, "
                                    "weather, train"},
            "capability": {"type": "string", "enum": ["can_book", "can_take_payment", "licensed_legal_ch",
                                                      "weather_forecast", "train_timetable"],
                           "description": "Optional. Omit it for hotels; tags are enough. weather_forecast finds "
                                          "the weather service, train_timetable the train timetable."},
        },
    ),
    function(
        "call_tool",
        "Call a signed tool on a verified node (A2T). The response is signature-checked.",
        {
            "node_id": {"type": "string"},
            "tool": {"type": "string", "enum": sorted(READ_TOOLS)},
            "args": {"type": "object",
                     "description": "get_availability: {date: YYYY-MM-DD, guests: int}; get_policies: {}; "
                                    "get_forecast (weather service): {place, date: YYYY-MM-DD}; get_connections "
                                    "(train timetable): {origin, destination, date: YYYY-MM-DD, time: HH:MM, "
                                    "arrive_by: bool (time is the latest arrival)}"},
        },
        ["node_id", "tool"],
    ),
    function(
        "ask_agent",
        "Ask a verified node's own agent a question its signed facts do not settle (A2A). "
        "Returns a signed answer and possibly a commitment (a priced promise you can book as an extra).",
        {"node_id": {"type": "string"}, "question": {"type": "string"}},
        ["node_id", "question"],
    ),
    function(
        "book",
        "Book a room on a verified node. Needs a get_availability for that date first. "
        "Waits until the user approves or declines on their phone.",
        {
            "node_id": {"type": "string"},
            "date": {"type": "string", "description": "YYYY-MM-DD; omit with use_agreement"},
            "room_type": {"type": "string", "description": "omit with use_agreement"},
            "guest_name": {"type": "string"},
            "extras": {"type": "array", "items": {"type": "string"},
                       "description": "'item' names of commitments from ask_agent to include; "
                                      "never with use_agreement"},
            "use_agreement": {"type": "boolean",
                              "description": "book exactly the deal agreed with this hotel: its room, night, "
                                             "rate, extras and price (no get_availability, room_type, date or "
                                             "extras needed)"},
        },
        ["node_id", "guest_name"],
    ),
    function(
        "pay",
        "Pay one of a hotel's charges listed in its policies (e.g. the city tax) for a confirmed booking. "
        "The hotel sets the amount. Uses the user's mandate if they allowed it, otherwise the phone asks.",
        {
            "node_id": {"type": "string"},
            "purpose": {"type": "string", "description": "the charge's purpose, e.g. \"city tax\""},
            "booking_id": {"type": "string"},
        },
        ["node_id", "purpose", "booking_id"],
    ),
    function(
        "end_conversation",
        "Close Tuttie's card in the wallet, like the user swiping it down. Use it when the user says "
        "goodbye or is done (bye, see you, that's all, thanks that's it, tschüss, ciao); answer with a "
        "very short goodbye.",
        {},
    ),
]


def same_room(a: str, b: str) -> bool:
    """True if two room type names mean the same room ("Double room" is "double")."""
    def norm(name: str) -> str:
        return re.sub(r"\s+room$", "", name.strip().lower())
    return norm(a) == norm(b)


def describe_deal(deal: dict, date: str) -> str:
    """An agreement's terms in one line for the phone and the LLM: room, night, rate, extras."""
    text = f"{deal.get('room_type') or deal['item']} room, night of {date}"
    if deal.get("rate"):
        text += f", {deal['rate']}"
    if deal.get("includes"):
        text += f", with {', '.join(deal['includes'])}"
    return text


def agreement_conflicts(deal: dict, booked_date: str, room_type: str, date: str, extras: list[str] | None) -> list[str]:
    """What in the LLM's book arguments would change a signed agreement (empty: nothing)."""
    conflicts = []
    if room_type and deal.get("room_type") and not same_room(room_type, deal["room_type"]):
        conflicts.append(f"room_type {room_type!r}")
    if date and date != booked_date:
        conflicts.append(f"date {date}")
    if extras:
        conflicts.append(f"extras {extras}")
    return conflicts


def booked_other_terms(confirmation: dict, amount: float, terms: dict | None) -> list[str]:
    """Where a signed confirmation differs from what the user approved (empty: it matches)."""
    total = confirmation.get("total_chf")
    numeric = isinstance(total, (int, float)) and not isinstance(total, bool)
    differ = [] if numeric and round(total, 2) == round(amount, 2) else ["total_chf"]
    if terms is not None:  # room, night and rate were approved as plain text (plain_term)
        plain = {key: None if confirmation.get(key) is None else plain_term(confirmation[key])
                 for key in ("room_type", "date", "rate")}
        plain["offer_id"] = confirmation.get("offer_id")
        differ += [key for key in ("room_type", "date", "rate", "offer_id") if key in terms and plain[key] != terms[key]]
        extras = confirmation.get("extras", [])  # no extras listed: nothing was included
        if "includes" in terms and (not isinstance(extras, list) or sorted(map(plain_term, extras)) != sorted(terms["includes"])):
            differ.append("includes")  # an approved extra dropped (or one added) is not what the user approved
    return differ


@dataclass
class Verified:
    """A node response that passed the trust gate: its record, verdict and signed envelope."""
    record: dict
    verdict: dict
    envelope: dict

    @property
    def payload(self) -> dict:
        return self.envelope["payload"]


# What a hotel's signed get_policies tells that the user may ask about later; photos and the
# rating are left out to keep the facts note small.
POLICY_FACTS = ("address", "distance_to_basel_sbb_m", "quiet_note", "policies", "amenities", "charges")


def policy_facts(payload: dict | None) -> dict | None:
    """The answerable part of a hotel's signed policies, or None if they were not fetched."""
    if not payload:
        return None
    return {key: payload[key] for key in POLICY_FACTS if payload.get(key) is not None}


def load_authorities() -> dict:
    """The trusted authorities from data/authorities.json, by issuer id."""
    return {a["issuer"]: a for a in json.loads(AUTHORITIES_PATH.read_text())}


def rejected(record: dict, reason: str) -> dict:
    """What the LLM sees instead of a node that failed verification."""
    return {"node_id": record.get("node_id"), "name": record.get("name"), "rejected": True, "reason": reason}


def node_view(record: dict, verdict: dict) -> dict:
    """What the LLM gets to know about a verified node."""
    return {
        "node_id": record["node_id"],
        "name": record["name"],
        "kind": record["kind"],
        "trust_tier": verdict["tier"],
        "uid": verdict["uid"],  # only set when the commercial register vouched for it
        "verified_by": [s["issuer"] for s in verdict["seals"]],
        "capabilities": verdict["capabilities"],
        "tags": record["tags"],
    }


def broken_reason(verdict: dict) -> str:
    """A short reason why a node's seals failed, for the LLM and the timeline."""
    failed = [f"{s['issuer']}/{s['tier']}" for s in verdict["seals"] if not s["valid"]]
    return f"seal does not verify: {', '.join(failed)}" if failed else "no seals"


def verified_summary(record: dict, verdict: dict) -> str:
    """Timeline text for a node whose seals verified; grey nodes are called untrusted."""
    if verdict["tier"] != "grey":
        return f"{record['name']}: {verdict['tier']} seal verified"
    signed = "no seals (unsigned)" if not verdict["seals"] else "self-signed only"
    unlicensed = [c for c in record["capabilities"] if c not in verdict["capabilities"] and c.startswith("licensed_")]
    claim = f", claims {', '.join(unlicensed)} without a valid licence" if unlicensed else ""
    return f"{record['name']}: {signed}, untrusted{claim}"


def summarize(tool: str, payload: dict) -> str:
    """A one-line timeline summary of a signed tool response."""
    if payload.get("rooms"):
        rooms = ", ".join(f"{r['room_type']} CHF {r['price_chf']}" for r in payload["rooms"])
        return f"{tool} {payload.get('date', '')}: {rooms}"
    if "policies" in payload:
        dogs = "dogs allowed" if payload["policies"].get("dogs_allowed") else "no dogs"
        return f"{tool}: {dogs}, {payload['policies'].get('late_arrival', '')}"
    if payload.get("status") == "refused":
        return f"{tool}: {payload.get('reason', 'refused')}"
    sample = " (sample data)" if "sample" in str(payload.get("source", "")) else ""
    if tool == "get_forecast" and "sky" in payload:  # services/weather.py
        return (f"Weather {payload['place']} {payload['date']}: {payload['sky']}, "
                f"{payload['temperature_min_c']:g}–{payload['temperature_max_c']:g} °C, "
                f"rain {payload['rain_chance_pct']} %{sample}")
    if tool == "get_connections" and payload.get("connections"):  # services/trains.py
        first = payload["connections"][0]
        return (f"Trains {payload['from']} → {payload['to']}: {first['departure']} → {first['arrival']} "
                f"({', '.join(first['trains']) or 'train'}){sample}")
    return tool


# Keys of book's result that Tuttie sets itself; a hotel's signed confirmation never fills them.
TUTTIE_KEYS = frozenset({"node_id", "source_step", "note", "charges_paid", "open_charges", "mismatch", "night"})


def night_said(date) -> str | None:
    """A night as it is said, with its weekday ("Saturday 14 November"), so the LLM never has to
    work the weekday out (it said "Friday" for a Saturday); None for anything but an ISO date."""
    try:
        day = datetime.strptime(str(date), "%Y-%m-%d")
    except ValueError:
        return None
    return f"{day:%A} {day.day} {day:%B}"


def offered_room(offer: dict) -> str | None:
    """The room type a hotel's signed offer is for: its room_type, else the start of its item
    ("double room 2026-11-14" -> "double"); None if it does not say."""
    if isinstance(offer.get("room_type"), str) and offer["room_type"]:
        return offer["room_type"]
    item = offer.get("item")
    if isinstance(item, str) and " room" in item:
        return item.split(" room", 1)[0].strip() or None
    return None


def finite_price(value, free_ok: bool = False) -> bool:
    """A real price: a finite number above zero (`free_ok`: or zero, e.g. a free add-on), not a
    bool (signed hotel data may hold anything, and math on a 400-digit integer raises OverflowError)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value) and (value >= 0 if free_ok else value > 0)
    except OverflowError:
        return False


def chf(value) -> str:
    """An amount for the timeline ("128", "12.5"), or "?" when it is not a real number."""
    return f"{value:g}" if finite_price(value, free_ok=True) else "?"


def listed(value) -> str:
    """A signed list of short words for the timeline; anything else is shown as "?"."""
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return ", ".join(value)
    return "?"

class Toolbox:
    """The tools the LLM can call; every result passes the APS trust gate first."""

    def __init__(self, http: httpx.AsyncClient, registry_url: str, bus: EventBus, approvals: ApprovalBook,
                 market: MarketDesk | None = None, mcp: McpLink | None = None, user: UserContext | None = None):
        self.http = http
        self.user = user or UserContext()
        self.mcp = mcp or McpLink()
        self.registry_url = registry_url.rstrip("/")
        self.bus = bus
        self.approvals = approvals
        self.authorities = load_authorities()
        self.market = market or MarketDesk(http, registry_url, bus, self.authorities)
        self.user_public_key = load_public_key("user")  # checks that Tuttie really acts for this user
        self.reset()

    def reset(self) -> None:
        # Signed facts remembered for booking, so prices never come from the LLM.
        """Forget the signed facts of the last conversation."""
        self.availability: dict[str, dict] = {}  # node_id -> last get_availability payload
        self.commitments: dict[str, list[dict]] = {}  # node_id -> signed A2A envelopes with a commitment
        self.agreements: dict[str, dict] = {}  # node_id -> the hotel's signed Agreement from the last negotiation
        self.seen: dict[str, int] = {}  # node_id -> timeline step of its registry check, shown once
        self.policies: dict[str, dict] = {}  # node_id -> payload of its signed get_policies
        if market := getattr(self, "market", None):
            market.forget()  # the old posting's offers are not this conversation's deals any more
        self.new_turn()

    def new_turn(self) -> None:
        """A new user message: the next negotiate call may bargain again (e.g. "try for less")."""
        self.bargained: dict | None = None  # this turn's negotiation: request_id, budget, outcomes

    async def dispatch(self, name: str, args: dict) -> dict:
        """Run a tool by name with the LLM's arguments; arguments that do not fit the tool are an error for the LLM."""
        tools = {"recall_context": self.recall_context, "post_request": self.post_request, "negotiate": self.negotiate, "search_registry": self.search_registry,
                 "call_tool": self.call_tool, "ask_agent": self.ask_agent, "book": self.book, "pay": self.pay,
                 "end_conversation": self.end_conversation, "current_deals": self.current_deals, "swipe_card": self.swipe_card}
        if name not in tools:
            return {"error": f"unknown tool {name}"}
        try:  # only the call itself: a TypeError inside a tool is a failure, not the LLM's mistake
            inspect.signature(tools[name]).bind(**args)
        except TypeError as error:
            return {"error": f"bad arguments for {name}: {error}"}
        return await tools[name](**args)

    async def current_deals(self) -> dict:
        """Return remembered verified facts, including agreements absent from raw availability,
        and each hotel's signed policies (check-in, pets, cancellation, address) when known, so
        follow-up questions about a hotel are answered from its signed facts, not from memory."""
        return {"deals": [{"node_id": item["node_id"], "name": item["name"],
                           "offered_chf": item["offer"]["price_chf"],
                           "agreement": self.agreements.get(item["node_id"], {}).get("payload"),
                           "policies": policy_facts(self.policies.get(item["node_id"]))}
                          for item in self.market.last_offers],
                "note": "A signed agreement overrides the original room rate. A final counter is not an agreement. "
                        "policies are the hotel's signed get_policies (null: not fetched yet, use call_tool)."}

    async def swipe_card(self, verdict: str) -> dict:
        if verdict not in {"like", "pass"}:
            return {"error": "verdict must be like or pass"}
        cards = next((e for e in reversed(self.bus.history)
                      if e["kind"] == "marketplace" and e["detail"].get("phase") in {"posted", "cards"}), None)
        pending_approval = next((e for e in reversed(self.bus.history) if e["kind"] == "approval"), None)
        if pending_approval and pending_approval["status"] == "pending":
            return {"error": "A payment approval is open. Use its approve/decline controls; do not swipe it."}
        if not cards or cards["detail"].get("phase") != "cards":
            return {"error": "There are no hotel cards to swipe. Ask for hotels first."}
        self.bus.emit("wallet", "verified", f"{verdict.title()} the visible hotel",
                      detail={"action": "swipe", "verdict": verdict, "cards_step": cards["step"]})
        return {"sent": verdict, "note": "The wallet applies this to its visible card. Do not book here; "
                "the wallet requests booking when the user finishes choosing."}

    async def end_conversation(self) -> dict:
        """Ask the wallet to close Tuttie's card (after the goodbye is said): a "close" event."""
        self.bus.emit("close", "verified", "Closing the card")
        return {"closing": True, "note": "now say a short goodbye (a few words)"}

    async def recall_context(self) -> dict:
        """The user's calendar, mail, messages and preferences (assistant/context.py)."""
        return await self.user.recall(self.bus)

    async def post_request(self, date: str, guests: int = 1, nights: int = 1, **request) -> dict:
        """Post the request on the market (MarketDesk.find), bargain with the hotels, then show
        them as cards with the agreed prices.

        A past night, a bad party size or more than one night is refused before anything is
        posted, so the LLM asks the user instead of booking something else silently.
        The wallet lets the user swipe through the cards; Tuttie then books the best liked deal.
        """
        if problem := stay_error(date, guests, nights):
            return {"error": problem}
        result = await self.market.find(date=date, guests=guests, **request)
        if "error" in result:
            return result
        result["night"] = night_said(date)  # say this, never a weekday of your own
        self.bargained = None
        self.agreements.clear()
        self.availability.clear()
        self.commitments.clear()
        if not self.market.last_offers:
            return result
        shown = card_order(self.market.last_offers, self.market.last_shortlist)
        # The agents bargain before the user sees anything: the cards show what was agreed.
        result["negotiation"] = await self.negotiate(self.market.last_budget, [o["node_id"] for o in shown])
        shortlisted = {o["offer"]["offer_id"] for o in self.market.last_shortlist}
        cards = []
        for item in shown:
            facts = await self.load_policies(item["node_id"])
            agreement = self.agreements.get(item["node_id"])
            cards.append(hotel_card(item, facts, self.market.last_request["constraints"]["requirements"],
                                    self.market.last_budget, item["offer"]["offer_id"] in shortlisted,
                                    agreement["payload"]["price_chf"] if agreement else None))
        self.bus.emit("marketplace", "verified", f"{len(cards)} hotels to choose from",
                      detail={"phase": "cards", "cards": cards})
        result["cards"] = [{"node_id": c["node_id"], "name": c["name"], "price_chf": c["price_chf"],
                            "room": offered_room(next((o["offer"] for o in self.market.last_offers
                                                       if o["node_id"] == c["node_id"]), {})),
                            "agreed_chf": c["agreed_chf"],
                            "rating": c["rating"], "shortlisted": c["shortlisted"],
                            "yes": [f["label"] for f in c["features"] if f["ok"]],
                            "no": [f["label"] for f in c["features"] if not f["ok"]]} for c in cards]
        return result

    async def negotiate(self, budget_chf: float | None = None, node_ids: list[str] | None = None) -> dict:
        """Bargain with dev member 2's negotiator (code/negotiation/) over the user's favourites
        (`node_ids`, any hotel that offered) or, without favourites, over the shortlist.

        Only the date and the needs are shared with the hotels; the budget is a private context
        item that the negotiator compares in code and never sends.
        """
        # Imported here: negotiation builds on this module (Toolbox, Verified).
        from negotiation.tuttie import BUDGET_LIMIT, TuttieNegotiator, best
        from assistant.subagents import SubagentPool

        if node_ids:
            chosen = [o for o in self.market.last_offers if o["node_id"] in node_ids]
            if not chosen:
                return {"error": f"none of {node_ids} sent an offer for the last request"}
        else:
            chosen = self.market.last_shortlist
        if not chosen:
            return {"error": "post a request first: there is no shortlist to negotiate"}
        request_id = self.market.last_request["request_id"]
        names = {o["node_id"]: o["name"] for o in chosen}
        done = self.bargained
        if (done and done["request_id"] == request_id and budget_chf in (None, done["budget"])
                and names.keys() <= done["outcomes"].keys()):
            # The model often calls negotiate right after post_request, which already bargained:
            # a second round would only replay the same haggling. A new user message resets this.
            repeat = self.negotiation_result([done["outcomes"][n] for n in names], names)
            repeat["note"] = ("Already negotiated for this request in this turn (post_request did it): "
                              "these are its signed agreements. Do not negotiate again; use them.")
            return repeat
        needs = self.market.last_request["constraints"]
        context = Context().add("date", needs["date"], "public").add("requirements", needs["requirements"], "negotiation")
        if budget_chf is not None:
            context.add(BUDGET_LIMIT, budget_chf, "private")
        negotiator = TuttieNegotiator(SubagentPool(self), self.market.agent_id, load_signing_key(self.market.agent_id))
        outcomes = await negotiator.negotiate_all(chosen, context)
        winner = best(outcomes)
        self.agreements.update({o.node_id: o.agreement for o in outcomes if o.status == "agreed"})
        same = done and done["request_id"] == request_id and done["budget"] == budget_chf
        earlier = done["outcomes"] if same else {}
        self.bargained = {"request_id": request_id, "budget": budget_chf,
                          "outcomes": {**earlier, **{o.node_id: o for o in outcomes}}}
        summary = (f"Best agreement: {names[winner.node_id]} at CHF {winner.price_chf:g} "
                   f"(offered CHF {winner.offer_price_chf:g})") if winner else "No hotel agreed within the budget"
        self.bus.emit("marketplace", "verified" if winner else "declined", summary,
                      detail={"phase": "agreement", "agreement": winner.agreement if winner else None})
        return self.negotiation_result(outcomes, names)

    @staticmethod
    def negotiation_result(outcomes: list, names: dict[str, str]) -> dict:
        """What negotiate returns to the LLM: each hotel's outcome and the cheapest agreement."""
        from negotiation.tuttie import best

        winner = best(outcomes)
        return {
            "outcomes": [{"node_id": o.node_id, "hotel": names[o.node_id], "status": o.status,
                          "agreement": o.agreement["payload"] if o.agreement else None, "offered_chf": o.offer_price_chf,
                          "agreed_chf": o.price_chf, "rounds": o.rounds, "reason": o.reason} for o in outcomes],
            "best": {"hotel": names[winner.node_id], "price_chf": winner.price_chf,
                     "offer_id": winner.offer_id} if winner else None,
        }

    async def search_registry(self, tags: list[str] | None = None, capability: str = "") -> dict:
        """Find nodes and split them into verified and rejected; each node shows once on the timeline."""
        params = {"tags": ",".join(tags or []), "capability": capability}
        records = (await self.http.get(f"{self.registry_url}/search", params=params)).json()
        verified, refused = [], []
        for record in records:
            verdict = evaluate_record(record, self.authorities)
            if verdict["tier"] == "broken":
                reason = broken_reason(verdict)
                self.emit_once(record, "broken", f"{record['name']}: {reason}, ignored", verdict)
                refused.append(rejected(record, reason))
            else:
                status = "untrusted" if verdict["tier"] == "grey" else "verified"
                step = self.emit_once(record, status, verified_summary(record, verdict), verdict)
                verified.append({**node_view(record, verdict), "source_step": step})
        result = {"query": params, "verified": verified, "rejected": refused}
        if not records:
            everything = (await self.http.get(f"{self.registry_url}/search")).json()
            known = sorted({tag for record in everything for tag in record["tags"]})
            result["hint"] = f"No node has all these tags. Search with fewer tags; known tags: {known}"
        return result

    async def identity(self, agent_id: str) -> dict:
        """The verified identity of a user agent (Tuttie), for the wallet to show.

        Checks the agent's seals like any node and, on top, that the user's key signed
        a delegation for exactly this agent and key. Not shown on the timeline.
        """
        found = await self.lookup(agent_id)
        if found is None:
            return {"node_id": agent_id, "rejected": True, "reason": "not in the registry"}
        record, verdict = found
        if verdict["tier"] == "broken":
            return rejected(record, broken_reason(verdict))
        delegation = record.get("delegation") or {}
        acts_for_user = verify_delegation(delegation, self.user_public_key, record["node_id"], record["public_key"])
        return {
            **node_view(record, verdict),
            "acts_for_user": acts_for_user,
            "scopes": delegation.get("scopes", []) if acts_for_user else [],
            "delegation_expires_at": delegation.get("expires_at") if acts_for_user else None,
        }

    def emit_once(self, record: dict, status: str, summary: str, verdict: dict) -> int:
        """Show a node's registry check on the timeline only the first time it is found."""
        if record["node_id"] not in self.seen:
            event = self.bus.emit("registry", status, summary, record, verdict["seals"],
                                  {"capabilities": verdict["capabilities"]})
            self.seen[record["node_id"]] = event["step"]
        return self.seen[record["node_id"]]

    async def lookup(self, node_id: str) -> tuple[dict, dict] | None:
        """A node's registry record and trust verdict, or None if it is unknown."""
        if not NODE_ID.match(node_id):
            return None
        response = await self.http.get(f"{self.registry_url}/nodes/{node_id}")
        if response.status_code != 200:
            return None
        record = response.json()
        return record, evaluate_record(record, self.authorities)

    async def verified_post(self, node_id: str, path: str, body: dict, kind: str, label: str,
                            headers: dict | None = None) -> Verified | dict:
        """Check the node's seals, POST to one of its agent endpoints, and verify the signed reply.

        Agent conversations are only held with gold or blue nodes: the deployment's agent key
        (aps/agent_key.py) must never reach a grey node, which could replay it elsewhere.
        Returns Verified, or a rejection dict for the LLM (already shown on the timeline).
        """
        async def send(record: dict) -> dict:
            response = await self.http.post(f"{record['endpoint']}{path}", json=body,
                                            headers={**agent_key.headers(), **(headers or {})})
            return response.json()
        return await self.verified(node_id, send, kind, label, tiers=("gold", "blue"))

    async def verified_mcp(self, node_id: str, tool: str, args: dict, kind: str, label: str) -> Verified | dict:
        """Check the node's seals, call one of its MCP tools, and verify the signed reply."""
        async def send(record: dict) -> dict:
            return await self.mcp.call(record["endpoint"], tool, args)
        return await self.verified(node_id, send, kind, label)

    async def verified(self, node_id: str, send, kind: str, label: str,
                       tiers: tuple[str, ...] = ("gold", "blue", "grey")) -> Verified | dict:
        """The trust gate around one call: seals first (the node's tier must be in `tiers`),
        then `send(record)`, then the envelope."""
        found = await self.lookup(node_id)
        if found is None:
            return {"node_id": node_id, "rejected": True, "reason": "not in the registry"}
        record, verdict = found
        if verdict["tier"] == "broken":
            reason = broken_reason(verdict)
            self.bus.emit(kind, "broken", f"{label} refused: {reason}", record, verdict["seals"])
            return rejected(record, reason)
        if verdict["tier"] not in tiers:
            self.bus.emit(kind, "untrusted", f"{label} not sent: {record['name']} has no verified seal",
                          record, verdict["seals"])
            return rejected(record, "agent conversations need a verified (gold or blue) seal")

        try:
            envelope = await send(record)
        except (httpx.HTTPError, McpCallFailed, ValueError) as error:
            self.bus.emit(kind, "broken", f"{label}: {record['name']} did not answer", record, verdict["seals"])
            return rejected(record, f"unreachable: {error}")
        if not verify_envelope(envelope, record["public_key"], expected_node_id=node_id):
            self.bus.emit(kind, "broken", f"{label}: response signature invalid, dropped", record, verdict["seals"])
            return rejected(record, "response signature does not verify")
        if not is_fresh(envelope["timestamp"], MAX_REPLY_AGE_S):
            self.bus.emit(kind, "broken", f"{label}: signed reply is outdated, dropped", record, verdict["seals"])
            return rejected(record, "signed reply is outdated (possible replay)")
        return Verified(record, verdict, envelope)

    async def signed_call(self, tool: str, args: dict) -> dict:
        """A call of an action tool signed with Tuttie's key, with the user's delegation attached."""
        agent_id = self.market.agent_id
        found = await self.lookup(agent_id)
        delegation = found[0].get("delegation") if found else None
        return sign_call(tool, args, agent_id, load_signing_key(agent_id), delegation)

    def emit_verified(self, kind: str, summary: str, result: Verified) -> int:
        """Signature checked; the step is still "untrusted" when the node itself is only grey."""
        status = "untrusted" if result.verdict["tier"] == "grey" else "verified"
        event = self.bus.emit(kind, status, summary, result.record, result.verdict["seals"],
                              {"timestamp": result.envelope["timestamp"], "payload": result.payload})
        return event["step"]

    async def call_tool(self, node_id: str, tool: str, args: dict | None = None) -> dict:
        """Call a read-only tool on a node and return its verified payload."""
        if tool not in READ_TOOLS or not TOOL_NAME.match(tool):
            return {"error": f"tool {tool} is not available through call_tool"}
        result = await self.verified_mcp(node_id, tool, args or {}, "a2t", tool)
        if not isinstance(result, Verified):
            return result
        if tool == "get_availability" and result.payload.get("status") != "refused":
            self.availability[node_id] = result.payload  # a refusal must not replace offered rooms
        step = self.emit_verified("a2t", summarize(tool, result.payload), result)
        return {"node_id": node_id, "trust_tier": result.verdict["tier"], "source_step": step, "data": result.payload}

    def private_amounts(self) -> set[int]:
        """The user's private amounts (the budget): from the last posting and from private context
        items that name a CHF amount. Free text to a business must not contain them (bug #18)."""
        amounts = {int(self.market.last_budget)} if self.market.last_budget else set()
        for items in self.user.data.values():
            for item in items if isinstance(items, list) else []:
                if isinstance(item, dict) and item.get("visibility") == "private":
                    amounts |= {int(n) for n in re.findall(r"CHF\s*(\d+)", str(item.get("what", "")))}
        return amounts

    async def ask_agent(self, node_id: str, question: str) -> dict:
        """Ask a node's own agent (A2A); a commitment in the reply is kept for booking.

        A question that names the private budget is not sent: code checks it, not the prompt."""
        if any(re.search(rf"(?<![\d.]){n}(?!\d)", question) for n in self.private_amounts()):
            return {"error": "not sent: the question names the user's private budget; ask without it"}
        # Only the posted night (public: it is in the signed request) so the hotel's commitment
        # holds for that night; never the budget or other private context.
        posted = self.market.last_request["constraints"].get("date") if self.market.last_request else None
        context = {"date": posted} if isinstance(posted, str) else {}
        result = await self.verified_post(node_id, "/agent", {"question": question, "context": context}, "a2a", "ask_agent")
        if not isinstance(result, Verified):
            return result
        reply = result.payload
        summary = f"Q: {question}  A: {reply.get('answer', '')}"
        if commitment := reply.get("commitment"):
            self.commitments.setdefault(node_id, []).append(result.envelope)
            summary += f"  Commitment: {commitment['item']}, CHF {chf(commitment['price_chf'])}"
        step = self.emit_verified("a2a", summary, result)
        return {"node_id": node_id, "trust_tier": result.verdict["tier"], "source_step": step, **reply}

    async def book(self, node_id: str, date: str = "", room_type: str = "", guest_name: str = "",
                   extras: list[str] | None = None, use_agreement: bool = False) -> dict:
        """Book a room: compute the total from signed facts only, wait for the user's signed
        approval on the phone, then let the node confirm the booking.

        With `use_agreement`, the booking is the hotel's signed Agreement from the last
        negotiation, exactly: its room type, night, rate, inclusions and price, which the node
        redeems once (negotiation/agreement.py). Arguments that would change any of them are
        refused with an error instead of being booked.
        """
        found = await self.lookup(node_id)
        # A booking takes payment, which untrusted (grey) nodes never get.
        if found is None or not {"can_book", "can_take_payment"} <= set(found[1]["capabilities"]):
            return {"node_id": node_id, "rejected": True,
                    "reason": "node is not trusted for bookings and payments (needs a gold or blue seal)"}
        record, verdict = found

        if use_agreement:
            agreement = self.agreements.get(node_id)
            if agreement is None:
                # The user chose it anyway: booking does not need a deal, only the phone's approval.
                return {"error": f"no signed agreement with {node_id}: book it without use_agreement, with "
                                 "date (the posted night) and room_type from call_tool get_availability (the room "
                                 "and rate of its offer on the card, else the cheapest fitting one), after ask_agent for one commitment for the special needs; "
                                 "do not ask the user"}
            deal = agreement["payload"]
            posted = self.market.last_request["constraints"]["date"] if self.market.last_request else None
            booked_room, booked_date = deal.get("room_type") or room_type, deal.get("date") or posted or date
            conflicts = agreement_conflicts(deal, booked_date, room_type, date, extras)
            if conflicts:
                return {"error": f"the signed agreement with {record['name']} is for {describe_deal(deal, booked_date)}; "
                                 f"{', '.join(conflicts)} would change it. Call book again with use_agreement=true "
                                 "and without room_type, date or extras, or ask the user before booking anything else.",
                        "agreement": deal}
            if not booked_room:
                return {"error": "the agreement names no room type: pass the room_type of the offer"}
            terms = None
            if deal.get("rate") is not None:
                terms = booking_terms(booked_room, booked_date, deal["rate"], deal["includes"], deal["offer_id"])
            amount = deal["price_chf"]
            if not finite_price(amount):
                return {"error": f"the signed agreement with {record['name']} has no usable price"}
            summary = f"Book {record['name']}: {describe_deal(deal, booked_date)} = CHF {amount:g} (negotiated)"
            return await self._approve_and_book(record, verdict, booked_date, booked_room, guest_name, [], amount,
                                                summary, agreement, terms)

        if not date or not room_type:
            return {"error": "pass date and room_type (or use_agreement=true to book a negotiated deal)"}
        availability = self.availability.get(node_id)
        if not availability or availability.get("date") != date:
            return {"error": f"call get_availability on {node_id} for {date} first"}
        card = next((o["offer"] for o in self.market.last_offers if o["node_id"] == node_id), None)
        if card is not None and (offered := offered_room(card)) and offered != room_type:
            # The user liked the card, so the booking is for the card's room (its rate may differ).
            return {"error": f"{record['name']}'s card offer is for the {offered} room: book room_type "
                             f"{offered!r}, or tell the user that room differs from the card"}
        room = next((r for r in availability["rooms"] if r["room_type"] == room_type), None)
        if room is None:
            return {"error": f"room_type must be one of {[r['room_type'] for r in availability['rooms']]}"}
        offered = {env["payload"]["commitment"]["item"]: env for env in self.commitments.get(node_id, [])}
        missing = [item for item in extras or [] if item not in offered]
        if missing:
            return {"error": f"unknown extras {missing}; signed commitments available: {list(offered)}"}

        chosen = [offered[item] for item in extras or []]
        add_ons = [env["payload"]["commitment"].get("price_chf") for env in chosen]  # may be free
        if not finite_price(room.get("price_chf")) or not all(finite_price(p, free_ok=True) for p in add_ons):
            return {"error": f"{record['name']}'s signed prices are not usable numbers; do not book it"}
        amount = room["price_chf"] + sum(env["payload"]["commitment"]["price_chf"] for env in chosen)
        parts = [f"{room_type} CHF {room['price_chf']:g} ({room['rate']})"]
        parts += [f"{env['payload']['commitment']['item']} CHF {env['payload']['commitment']['price_chf']:g}"
                  for env in chosen]
        summary = f"Book {record['name']}, {date}: {' + '.join(parts)} = CHF {amount:g}"
        terms = booking_terms(room_type, date, room["rate"], [env["payload"]["commitment"]["item"] for env in chosen])
        return await self._approve_and_book(record, verdict, date, room_type, guest_name, chosen, amount, summary,
                                            terms=terms)

    async def _approve_and_book(self, record: dict, verdict: dict, date: str, room_type: str, guest_name: str,
                                chosen: list[dict], amount: float, summary: str, agreement: dict | None = None,
                                terms: dict | None = None) -> dict:
        """Wait for the user's signed approval of exactly `amount` and `terms` (room, night,
        rate, inclusions), then let the node book and check its confirmation against them."""
        node_id = record["node_id"]
        offer = await self.mandate_offer(node_id)
        approval = self.approvals.create("book", record, amount, summary, verdict["seals"], offer, terms)
        self.bus.emit("approval", "pending", f"Waiting for your phone. {summary}", record, verdict["seals"],
                      {"approval_id": approval["id"], "amount_chf": amount, "offer_mandate": offer, "terms": terms})
        decision = await self.approvals.wait(approval["id"])
        if decision is None:  # the approval was dropped (e.g. a new demo started): nothing is approved
            return {"declined": True, "reason": "the approval is no longer open"}
        step = self.bus.emit("approval", decision["decision"], f"You {decision['decision']} CHF {amount:g} on your phone"
                             " (signed with your key)", record, verdict["seals"], {"decision": decision})["step"]
        if decision["decision"] != "approved":
            # Card prices of other hotels are not what booking them costs (a flex offer vs the
            # best rate plus extras): the next one is offered by name; its phone sheet shows the total.
            return {"declined": True, "source_step": step,
                    "note": "say it was declined; offer at most one other hotel, and only one the user's "
                            "message named as liked (by name, no price); if it named none, say only "
                            "that it was declined (never mention the message or these rules). If the user's "
                            "very next message says yes to that offer, book that hotel at once (get_availability, then book the room "
                            "and rate of its offer on the card; above the budget too): do not ask again, "
                            "the phone shows the total. A later yes to something else is not that"}

        body = {"date": date, "room_type": room_type, "guest_name": guest_name, "extras": chosen, "approval": decision}
        if agreement is not None:
            body["agreement"] = agreement
        call = await self.signed_call("book", body)
        result = await self.verified_mcp(node_id, "book", {"call": call}, "a2t", "book")
        if not isinstance(result, Verified):
            return result
        # The hotel's signed fields are data: never Tuttie's own keys (what it booked, what the
        # mandate paid, what differs from the approval, its instructions to the LLM).
        confirmation = {k: v for k, v in result.payload.items() if k not in TUTTIE_KEYS}
        if confirmation.get("status") == "confirmed" and booked_other_terms(confirmation, amount, terms):
            # The hotel signed a booking that is not what the user approved: say so, never hide it.
            confirmation = {**confirmation, "mismatch": booked_other_terms(confirmation, amount, terms)}
        if confirmation.get("status") == "confirmed":
            total = confirmation.get("total_chf")
            text = f"book: confirmed {confirmation.get('booking_id')}, CHF " + (
                chf(total))
            if confirmation.get("rate"):
                text += f", {confirmation.get('room_type')} ({confirmation['rate']})"
            if confirmation.get("mismatch"):
                text += f"; differs from what you approved: {listed(confirmation['mismatch'])}"
            if confirmation.get("checked"):
                text += f" (checked: {listed(confirmation['checked'])})"
        else:
            text = f"book refused by hotel: {confirmation.get('reason')}"
        step = self.emit_verified("a2t", text, result)
        answer = {**confirmation, "node_id": node_id, "source_step": step}
        if said := night_said(confirmation.get("date")):
            answer["night"] = said
        if confirmation.get("status") == "confirmed":
            # Charges the user already allowed with a mandate are paid right away, without asking.
            for charge in await self.load_charges(node_id):
                if (node_id, charge["purpose"]) in self.approvals.mandates:
                    paid = await self.pay(node_id, charge["purpose"], confirmation["booking_id"])
                    answer.setdefault("charges_paid", []).append(paid)
                else:
                    answer.setdefault("open_charges", []).append(charge)
            # The user's message also named hotels for a decline; after a booking they are moot.
            answer["note"] = "booked: say it is booked and the total; do not offer other hotels"
        return answer

    async def mandate_offer(self, node_id: str) -> dict | None:
        """A mandate to offer with a booking: for the hotel's small charge (e.g. the city tax), if any.

        Only for a charge above CHF 0: a mandate is for a positive amount (aps/mandate.py)."""
        small = [c for c in await self.load_charges(node_id) if 0 < c["price_chf"] <= AUTO_PAY_LIMIT_CHF]
        if not small:
            return None
        charge = small[0]
        return {"agent_id": self.market.agent_id, "purpose": charge["purpose"], "max_chf": charge["price_chf"],
                "price_chf": charge["price_chf"]}

    async def load_policies(self, node_id: str) -> dict:
        """A hotel's signed policies (get_policies), kept for this conversation; {} if unavailable."""
        if node_id not in self.policies:
            result = await self.verified_mcp(node_id, "get_policies", {}, "a2t", "get_policies")
            self.policies[node_id] = result.payload if isinstance(result, Verified) else {}
        return self.policies[node_id]

    async def load_charges(self, node_id: str) -> list[dict]:
        """The charges a hotel lists in its signed policies."""
        return (await self.load_policies(node_id)).get("charges", [])

    async def pay(self, node_id: str, purpose: str, booking_id: str) -> dict:
        """Pay a hotel's charge for a booking: with the user's mandate if it covers it, else after
        the user's signed approval on the phone. The amount comes from the hotel's signed policies."""
        found = await self.lookup(node_id)
        if found is None or "can_take_payment" not in found[1]["capabilities"]:
            return {"node_id": node_id, "rejected": True, "reason": "node is not trusted for payments"}
        record, verdict = found
        charge = next((c for c in await self.load_charges(node_id) if c["purpose"] == purpose), None)
        if charge is None:
            return {"error": f"{record['name']} lists no charge for {purpose!r} in its signed policies"}
        amount = charge["price_chf"]
        mandate = self.approvals.mandates.get((node_id, purpose))
        refusal = "no mandate" if mandate is None else may_auto_pay(
            mandate, self.user_public_key, self.market.agent_id, record, self.authorities, amount, purpose)
        args = {"purpose": purpose, "booking_id": booking_id}
        if refusal is None:
            args["mandate"] = mandate
            how = "with your mandate, no phone needed"
        else:
            summary = f"Pay {record['name']}: {purpose} for {booking_id} = CHF {amount:g}"
            approval = self.approvals.create("pay", record, amount, summary, verdict["seals"],
                                             charge=payment_charge(purpose, booking_id))
            self.bus.emit("approval", "pending", f"Waiting for your phone. {summary}", record, verdict["seals"],
                          {"approval_id": approval["id"], "amount_chf": amount})
            decision = await self.approvals.wait(approval["id"])
            if decision is None:  # the approval was dropped (e.g. a new demo started): nothing is approved
                return {"declined": True, "reason": "the approval is no longer open"}
            step = self.bus.emit("approval", decision["decision"], f"You {decision['decision']} CHF {amount:g} on your phone"
                                 " (signed with your key)", record, verdict["seals"], {"decision": decision})["step"]
            if decision["decision"] != "approved":
                return {"declined": True, "source_step": step}
            args["approval"] = decision
            how = "approved on your phone"

        result = await self.verified_mcp(node_id, "pay", {"call": await self.signed_call("pay", args)}, "payment", "pay")
        if not isinstance(result, Verified):
            return result
        receipt = result.payload
        if receipt.get("status") == "paid":
            text = f"pay: {purpose} CHF {chf(receipt.get('amount_chf'))} paid {how} (checked: {', '.join(receipt['checked'])})"
        else:
            text = f"pay refused by {record['name']}: {receipt.get('reason')}"
        step = self.emit_verified("payment", text, result)
        return {"node_id": node_id, "source_step": step, **receipt}
