"""hunt10: a free (CHF 0) signed add-on (Rheinblick "late check-in after 22:00", Gästehaus
"late arrival with dog", Gundeli child bed: all price_chf 0 in data/nodes) must not block booking.
finite_price() refuses 0, so book(..., extras=[free item]) returns "not usable numbers"."""

import asyncio

import test_tools as tt


def test_a_free_signed_extra_still_books():
    tt.NODE_REPLIES["/agent"] = {"answer": "Fine.", "commitment": {
        "item": "late check-in after 22:00", "price_chf": 0, "conditions": [],
        "valid_until": "2026-11-15T00:00:00Z"}}
    try:
        toolbox, bus, _ = tt.make_toolbox()

        async def flow():
            await toolbox.call_tool(tt.RHEINBLICK, "get_availability", {"date": "2026-11-14"})
            await toolbox.ask_agent(tt.RHEINBLICK, "Late arrival?")
            booking = asyncio.create_task(
                toolbox.book(tt.RHEINBLICK, "2026-11-14", "double", "Alex Muster", ["late check-in after 22:00"]))
            await asyncio.sleep(0.05)
            pending = list(toolbox.approvals.pending.values())
            if not pending:
                return await booking
            assert pending[0]["amount_chf"] == 180
            toolbox.approvals.decide(pending[0]["id"], "approved")
            return await booking

        result = asyncio.run(flow())
        assert "error" not in result, result
    finally:
        tt.NODE_REPLIES["/agent"] = {"answer": "Fine.", "commitment": {
            "item": "late check-in with dog", "price_chf": 15, "conditions": [],
            "valid_until": "2026-11-15T00:00:00Z"}}
