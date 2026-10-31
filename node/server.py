"""Generic business node: one FastAPI app, started once per config in data/nodes/.

Usage: python -m node.server --config data/nodes/hotel-rheinblick.json [--port 8001]

Every response is a signed envelope from this node's key (keys/<node_id>.json).
Tools answer only from the config's "facts".
"""

import argparse
import json
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel

from aps import load_signing_key, sign_envelope


class AvailabilityRequest(BaseModel):
    date: str
    guests: int = 1


def create_app(config: dict) -> FastAPI:
    node_id = config["node_id"]
    facts = config.get("facts", {})
    signing_key = load_signing_key(node_id)
    app = FastAPI(title=config["name"])

    def signed(payload: dict) -> dict:
        return sign_envelope(node_id, payload, signing_key)

    @app.post("/tools/get_availability")
    def get_availability(req: AvailabilityRequest) -> dict:
        rooms = [
            {k: room[k] for k in ("room_type", "price_chf", "rate")}
            for room in facts.get("rooms", []) if room.get("available")
        ]
        return signed({
            "tool": "get_availability",
            "hotel": config["name"],
            "date": req.date,
            "guests": req.guests,
            "currency": "CHF",
            "rooms": rooms,
        })

    @app.post("/tools/get_policies")
    def get_policies() -> dict:
        return signed({
            "tool": "get_policies",
            "hotel": config["name"],
            "address": facts.get("address"),
            "distance_to_basel_sbb_m": facts.get("distance_to_basel_sbb_m"),
            "quiet": facts.get("quiet"),
            "quiet_note": facts.get("quiet_note"),
            "policies": facts.get("policies", {}),
        })

    return app


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--port", type=int)
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text())
    uvicorn.run(create_app(config), host="0.0.0.0", port=args.port or config["port"])


if __name__ == "__main__":
    main()
