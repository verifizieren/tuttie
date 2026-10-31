# Marketplace (issues #8, #9, #10) — not started

The reverse marketplace: the user's agent posts a signed **request**, matching business
agents answer with signed **offers**, the user's agent shortlists the best five and the
agents **negotiate** until there is an **agreement** the user approves on the phone.

- Messages: `documentation/formats.md`, section "DRAFT: marketplace messages".
- Port: 4010 (when it becomes a service).
- Reuse: `aps/` for every signature and check (never sign by hand), `registry/` to find
  nodes by tags, `node/server.py` as the place where business agents answer requests and
  counter-offers, `assistant/approvals.py` for the final phone approval.
- Business limits (`facts.negotiation`) stay inside the node; they are never sent.
