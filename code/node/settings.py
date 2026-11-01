"""What a business owner may change about their agent, and how a change is checked and applied.

The owner's *settings* are a slice of the node config:

    facts                profile, address and directions, rooms and prices, policies, charges,
                         add-ons and the private negotiation limits (`facts.*`)
    persona              the agent's name, role, tone and priorities (never its boundaries)
    respond_to_postings  whether the agent is woken by new marketplace postings

Everything else stays fixed: UID, seals, tags, capabilities, the agent's tools and its
boundaries (they protect the private limits). Changing those needs new seals or APS work.

Settings are validated here, strictly, because they end up in prompts, prices and bargaining
limits: `validate` returns the clean settings or a list of {path, message} errors, `apply`
writes them into a live config, `canonical` is the one JSON form used to compare versions.
The server and the agents never see unchecked owner input.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StrictBool, StrictInt, StringConstraints, ValidationError

from node.agent import DEFAULT_WAKES_ON

POSTING_EVENTS = ["posting.created", "posting.updated"]
STANDARD_ROOM = "double"  # the room the negotiation floor is set for (negotiation/rules.py)
# The persona fields an owner may set; `boundaries` stays as the config has it.
PERSONA_FIELDS = ("name", "role", "tone", "priorities")
EDITABLE_FACTS = ("profile", "address", "distance_to_basel_sbb_m", "how_to_get_there", "quiet", "quiet_note",
                  "facilities", "rooms", "policies", "charges", "add_ons", "negotiation")


def blank_to_none(value):
    """An empty text box means "not set"."""
    return None if isinstance(value, str) and not value.strip() else value


Short = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Long = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=600)]
OptShort = Annotated[Short | None, BeforeValidator(blank_to_none)]
OptLong = Annotated[Long | None, BeforeValidator(blank_to_none)]
Francs = Annotated[StrictInt, Field(ge=0, le=100_000)]
RoomType = Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, pattern=r"^[a-z0-9][a-z0-9 _-]{0,39}$")]
Slug = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[a-z0-9][a-z0-9-]{0,39}$")]
PolicyKey = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,39}$")]


class Strict(BaseModel):
    """Base for every settings model: unknown fields are errors, not silently dropped."""

    model_config = ConfigDict(extra="forbid")


class Profile(Strict):
    size: Literal["small", "medium", "large"]
    rooms_total: Annotated[StrictInt, Field(ge=1, le=10_000)]
    about: OptLong = None
    chain: OptShort = None


class Room(Strict):
    room_type: RoomType
    price_chf: Annotated[StrictInt, Field(ge=1, le=100_000)]
    rate: Short
    available: StrictBool = True
    note: OptShort = None


class Charge(Strict):
    purpose: Short
    price_chf: Annotated[StrictInt, Field(ge=1, le=100_000)]  # a charge of CHF 0 is not a charge
    note: OptShort = None


class AddOn(Strict):
    id: Slug
    item: Short
    price_chf: Francs
    conditions: Annotated[list[Short], Field(max_length=10)] = []


class Negotiation(Strict):
    floor_chf: Annotated[StrictInt, Field(ge=1, le=100_000)]
    max_rounds: Annotated[StrictInt, Field(ge=1, le=10)]


class Facts(Strict):
    profile: Profile | None = None
    address: OptShort = None
    distance_to_basel_sbb_m: Annotated[StrictInt, Field(ge=0, le=1_000_000)] | None = None
    how_to_get_there: OptLong = None
    quiet: StrictBool | None = None
    quiet_note: OptLong = None
    facilities: Annotated[list[Short], Field(max_length=30)] | None = None
    rooms: Annotated[list[Room], Field(max_length=30)] = []
    policies: Annotated[dict[PolicyKey, StrictBool | StrictInt | Short], Field(max_length=30)] = {}
    charges: Annotated[list[Charge], Field(max_length=20)] = []
    add_ons: Annotated[list[AddOn], Field(max_length=50)] = []
    negotiation: Negotiation | None = None


class Persona(Strict):
    name: OptShort = None
    role: OptShort = None
    tone: OptShort = None
    priorities: Annotated[list[Short], Field(max_length=10)] | None = None


class Settings(Strict):
    facts: Facts = Facts()
    persona: Persona | None = None
    respond_to_postings: StrictBool = True


def error_path(location: tuple) -> str:
    """A pydantic error location as the dotted path the owner view uses, e.g. facts.rooms.0.price_chf."""
    return ".".join(str(part) for part in location)


# Pydantic's error types in words an owner understands; other types keep pydantic's own wording.
FRIENDLY = {
    "missing": "This is required",
    "string_too_short": "This is required",
    "string_pattern_mismatch": "Use only letters, digits, spaces and dashes",
    "int_type": "Enter a whole number",
    "int_parsing": "Enter a whole number",
    "extra_forbidden": "This cannot be changed here",
    "literal_error": "Choose one of the options",
    "bool_type": "Choose yes or no",
}


def clean_message(error: dict) -> str:
    """An owner-readable message for one pydantic error."""
    return FRIENDLY.get(error["type"]) or error["msg"].removeprefix("Value error, ")


def cross_checks(settings: Settings) -> list[dict]:
    """Rules that span several fields; each error names the field it belongs to."""
    errors = []
    facts = settings.facts
    for name, items, key in (("rooms", facts.rooms, lambda r: r.room_type), ("add_ons", facts.add_ons, lambda a: a.id),
                             ("charges", facts.charges, lambda c: c.purpose.lower())):
        seen: set[str] = set()
        for index, item in enumerate(items):
            if key(item) in seen:
                errors.append({"path": f"facts.{name}.{index}", "message": f"{key(item)!r} is listed twice"})
            seen.add(key(item))
    open_rooms = [room for room in facts.rooms if room.available]
    if facts.negotiation and open_rooms:
        standard = next((r for r in open_rooms if r.room_type == STANDARD_ROOM), min(open_rooms, key=lambda r: r.price_chf))
        if facts.negotiation.floor_chf > standard.price_chf:
            errors.append({"path": "facts.negotiation.floor_chf",
                           "message": f"the lowest price cannot be above the {standard.room_type} room's price "
                                      f"(CHF {standard.price_chf})"})
    persona = settings.persona
    if persona and any(getattr(persona, field) for field in PERSONA_FIELDS):
        for field in ("name", "role"):
            if not getattr(persona, field):
                errors.append({"path": f"persona.{field}", "message": "the agent needs this"})
    return errors


def validate(raw) -> tuple[Settings | None, list[dict]]:
    """Check owner input: the clean Settings, or None with every error as {path, message}."""
    try:
        settings = Settings.model_validate(raw)
    except ValidationError as failure:
        return None, [{"path": error_path(e["loc"]), "message": clean_message(e)} for e in failure.errors()]
    errors = cross_checks(settings)
    return (None, errors) if errors else (settings, [])


def canonical(settings: Settings) -> dict:
    """The one JSON form of settings: what is stored, compared and shown."""
    return settings.model_dump(exclude_none=True)


def snapshot(config: dict) -> Settings:
    """The settings a node config currently has (version 0 is the committed config)."""
    facts = config.get("facts", {})
    agent = config.get("agent", {})
    persona = {k: v for k, v in agent.get("persona", {}).items() if k in PERSONA_FIELDS}
    wakes_on = agent.get("wakes_on", DEFAULT_WAKES_ON)
    return Settings.model_validate({
        "facts": {k: v for k, v in facts.items() if k in EDITABLE_FACTS},
        "persona": persona or None,
        "respond_to_postings": any(event in wakes_on for event in POSTING_EVENTS),
    })


def apply(config: dict, settings: Settings) -> None:
    """Write validated settings into a live config. Each part is replaced in one assignment,
    so a request being answered meanwhile sees either the old or the new value, never a mix."""
    facts = {k: v for k, v in config.get("facts", {}).items() if k not in EDITABLE_FACTS}
    facts.update(settings.facts.model_dump(exclude_none=True))
    agent = dict(config.get("agent", {}))
    persona = settings.persona.model_dump(exclude_none=True) if settings.persona else {}
    if persona:
        boundaries = agent.get("persona", {}).get("boundaries")
        agent["persona"] = {**persona, **({"boundaries": boundaries} if boundaries else {})}
    others = [e for e in agent.get("wakes_on", DEFAULT_WAKES_ON) if e not in POSTING_EVENTS]
    agent["wakes_on"] = (POSTING_EVENTS if settings.respond_to_postings else []) + others
    config["facts"] = facts
    config["agent"] = agent
