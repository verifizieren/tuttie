# Dev goals

What the dev team builds next and how we work. Concept: `documentation/concept.md`;
work areas and interfaces: `documentation/architecture.md`; message formats:
`documentation/formats.md`.

## How we work

- **Code quality first.** Small, readable modules with a short docstring each; comments
  where the *why* is not obvious; no clever code.
- **Test loops.** Every feature comes with tests (`code/tests/`, run `pytest -q`), and we
  run the real flow end to end regularly (`code/scripts/demo_headless.py`). Tests for
  `code/aps/` must always pass.
- **Documentation.** Update the docs in the same change as the code. Contracts in
  `documentation/formats.md` only change after telling the whole team.
- **Regular check-ups with the pitch and design team**, so what we build can be pitched
  the way the storyline needs it (`documentation/context/pitch/`). The demo is a run
  through the real app, never a separate demo build.
- **Small, clear commits.** The jury reviews the code and the commit history.

## Goal 1: the first marketplace, in two layers (issues #8, #9, #10)

A **reverse marketplace**: the user posts what they need, and businesses' agents apply to
that posting with offers.

| Layer | Who | What they do |
| --- | --- | --- |
| **Human layer** | people, in the wallet app | look at the marketplace: their postings, what is offered, the offers that came in, the state of the negotiation, and approve the final deal |
| **Agent layer** | agents, over the API | the user's agent puts up postings; business agents read matching postings and apply with signed offers; the user's agent picks from the offers and negotiates |

The human layer is the visual side of the wallet (`code/apps/wallet/`); the agent layer is
the marketplace service (`code/marketplace/`). Both show the same marketplace.

## Goal 2: the first agents

- **Tuttie**, our user agent: holds the user's full context and acts for them.
- **Three hotel agents** as the first example, deliberately of different sizes so small
  businesses visibly get a fair chance:
  - a big hotel (a branch of a chain),
  - a mid-sized hotel,
  - a small independent hotel.

Their facts, prices and negotiation limits live in their node configs
(`code/data/nodes/`); prices never come from an LLM.

## Goal 3: subagents with limited context

Tuttie keeps the full context, but it does not bargain itself: it **spawns a subagent per
negotiation** that only gets what that negotiation needs.

- Every piece of user information is classed as **public** (may go into the posting),
  **negotiation** (may be shared with this one business while bargaining) or **private**
  (never leaves Tuttie, e.g. the real budget limit or personal details).
- The subagent gets the posting, the offer it negotiates and the public and negotiation
  information, nothing private. Tuttie decides what is shared, and every shared item is
  visible on the timeline.
- The same applies on the business side: their limits (e.g. `facts.negotiation.floor_chf`)
  stay inside their node.

## Goal 4: MCP services for actions

Agents act through **MCP services** (tools such as posting, offering, booking and paying).
A service only executes an action when it carries the **right signatures**, exactly like
`book` today: the business's signed offer plus the user's signed approval
(`code/node/server.py`, `code/aps/approval.py`).

## Goal 5: APS, the secure agent protocol (issue #10)

- **Verified entities.** Businesses are verified through their **UID** (Swiss business
  identification number), vouched for by the commercial register (`handelsregister-bs`,
  gold). Corporates and platforms can additionally sign as themselves (e.g. `adobe`, blue).
- **Simple signing for now:** Ed25519 seals and signed envelopes as in `code/aps/`. The real
  government integration is simulated; the signatures and checks are real.
- **No signature, no action.** Unsigned (untrusted, grey) or forged (broken, red) agents can
  be shown but never transact.
