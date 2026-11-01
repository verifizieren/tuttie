# Tuttie in one page

BaselHack 2026, Adobe challenge "The Post-Website Business". Live: <https://web4.mendes.dev>.
Details: [concept](../../concept.md), [architecture](../../architecture.md),
[dev status](../dev/status.md).

## In one sentence

Tuttie is your agent in your phone's wallet: you say what you need, businesses' agents come to
you with signed offers, Tuttie drops the fakes, bargains for you, and you approve with one tap.

## The problem

- **For people:** finding a hotel, a lawyer or a craftsman means comparing dozens of websites,
  platforms and now AI answers, without knowing which claims are true. Fake listings and
  phishing look exactly like real offers.
- **For small businesses:** visibility goes to whoever pays the platforms or ranks highest.
  Two in three Swiss firms under ten people have no website at all (localsearch & HSLU,
  SME Digital Pulse 2025). When people ask an AI instead of searching, a small business has no
  way to be found, cited or represented correctly.

## The idea

The web splits into two layers. Websites stay for people. Next to them grows an **agent web**:
every business is a **signed node** with a verified identity, its facts, its tools and its own
agent. Agents talk to agents, and every message carries an **APS seal** (Agent Protocol Secure):
who sent it, which authorities vouch for it and what it may do.

| Seal | Meaning | What Tuttie does |
| --- | --- | --- |
| gold | vouched for by an official register (the commercial register with the Swiss UID, or a licensing body such as the bar association) | trusted |
| blue | vouched for by a company or platform | trusted |
| grey | unsigned or self-signed | shown, never transacts |
| red | forged or invalid | dropped: the user never sees it |

Scams are not blocked one by one; they become invisible, because they cannot sign.

## How it works (the flow)

1. **Request.** The user tells Tuttie what they need. Tuttie posts a signed request (with the
   user's signed delegation) on the marketplace.
2. **Offers.** The marketplace wakes the verified businesses whose agents subscribe to such
   requests; interested agents answer with signed offers. Prices come from the business's own
   configuration, never from an LLM.
3. **Trust check.** Tuttie verifies every seal and signature; forged offers are dropped.
4. **Shortlist and bargaining.** Tuttie picks the best offers and spawns one subagent per offer.
   The subagents bargain in parallel; each side keeps its limits private (the user's budget,
   the hotel's floor price) and the limits are compared in code, never shown to an LLM.
5. **Approval.** The user approves the final deal with one tap, signed with their own key.
   Nothing is booked or paid without it.
6. **Booking.** The business checks the user's signature and the signed agreement and confirms.

## Who benefits

- **People:** one request instead of fifty tabs; only verified offers; their own agent
  negotiates; nothing happens without their tap.
- **Small businesses:** their agent answers every matching request, day and night, in their own
  words, so a seven-room guesthouse competes with a 220-room chain on fit and price, not on ad
  budget. No website needed: a signature is.
- **Platforms and registries** get a new role: they vouch (seals) instead of owning the
  customer.

## What is built (1 Nov)

Working and tested (336 Python tests, plus the wallet's and owner view's own tests): APS
signing with Ed25519 seals, Swiss UIDs, signed approvals, delegations, signed calls and an
action gate for `book` and `pay`; the registry; business nodes with tools over MCP; one
company-agent object for every business with personas and private limits; three hotel agents
(Alpina Grand Basel, large chain; Hotel Rheinblick, medium; Gästehaus am Rhein, small, owner
Anna); the marketplace agent layer (signed postings in, signed offers out); sessions with
memory and parallel subagents; Tuttie posting signed requests with a private budget and
bargaining with the hotels within their private limits before the user sees the offers;
booking a signed agreement after the user approves exactly that price; the city tax paid with
the user's mandate; Tuttie's own sealed identity; sealed weather and train services.
The wallet is connected: spoken or typed requests, the hotels as a swipe deck with agreed
prices, approvals with a Face ID-style confirmation, the signed booking. Voice is live
(self-hosted LiveKit, ElevenLabs). The owner view lets a business change prices, extras,
negotiation limits and its agent, deployed as versions.

The presentation QR page (`code/apps/qr/`) shows the numbers, the idea, the business
case and a self-playing demo of the wallet; it is on branch `presentation-site`, not merged yet.

Not yet: the demo runner (`code/demo/`); voice confirmed on a real iPhone. See [status.md](../dev/status.md).

## The pitch

Three minutes, live through the real wallet, almost no text on screen, one continuous camera.
Storyline: [storyline.md](storyline.md). Research and checklists: [playbook.md](playbook.md).
Status and next steps for the pitch: [handoff.md](handoff.md).

Closing line: *"In 2000 you needed a website. In 2033 you need a signature."*

## Team

Jonas, Stan (research), Sebastian, Thomas (pitch), Max, Chris (dev).
