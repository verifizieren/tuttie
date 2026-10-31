# Owner view (issue #5) — not started

A simple page for non-technical business owners to edit their agent's presence:
description, offers and prices, add-ons, negotiation limits.

- Data: the node config `data/nodes/<node>.json` (`facts`). Facts are not part of a seal,
  so editing them never breaks the seals; changing `capabilities` would need new seals.
- Needs an owner API (to define, e.g. on the node): read and update the facts, authorised
  with the owner's key.
- Static page served at `/owner/`, shared UI pieces in `apps/shared/`.
