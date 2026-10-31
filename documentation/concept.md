# Tuttie: concept and demo strategy

## In one sentence

Tuttie is your agent in your phone's wallet: you say what you need, businesses' agents come
to you with signed offers, your agent picks the best few and negotiates for you, and you
approve with one tap. Every message is signed, so fakes simply do not show up.

## Why it matters

- **For people:** one request instead of comparing fifty websites; nothing happens without
  your approval; scams are invisible because unsigned or forged answers are dropped.
- **For small businesses** (issue #5): today they lose to big platforms on visibility. On
  Tuttie their agent answers every matching request and can negotiate with many customers at
  once, so they are always in the running. Owners set the rules (prices, limits) in plain
  language and can change their agent's presence at any time.

## The flow (reverse marketplace, issue #8)

1. **Request.** The user tells their wallet agent (by voice) what they need, e.g. a quiet,
   dog-friendly hotel near Basel SBB for 14 Nov under CHF 200. The agent posts a signed
   request on the platform.
2. **Offers.** Business agents whose profile matches answer with **signed offers**.
3. **Trust check.** The user's agent verifies every seal and signature
   (`documentation/formats.md`). Forged offers are dropped (red), untrusted ones are shown
   but never booked (grey).
4. **Shortlist.** The user's agent picks the five offers that fit best.
5. **Negotiation.** The agents bargain: counter-offers, add-ons, conditions. Business agents
   stay within limits their owner set, which they never reveal.
6. **Approval.** The user approves the final deal on the phone; the decision is signed with
   the user's key.
7. **Deal.** The business confirms with a signed booking. Totals come only from signed
   messages, never from an LLM.

## Apps

| App | What the user sees | Issue |
| --- | --- | --- |
| Wallet (phone) | The web app is the wallet itself, built for phone screens and kept minimal: an Apple Wallet-like stack of cards, the Tuttie agent card plus two generic bank cards (no real details). Agents appear as procedurally generated avatars. Swiping the agent card up opens the voice agent. Offers, negotiation and approvals appear here. | #2 |
| Owner view | A business owner edits their agent's presence: description, offers, negotiation limits. | #5 |
| Presentation site | The pitch as a website with a QR code. During the pitch it shows a minimal concept; a timer/counter unlocks more content afterwards; at the end an Apple-style scroll leads into the live demo. | #1, #6 |
| Behind the scenes (to build) | Every signed step with its seals, live from the timeline (`GET /events`). Useful on the projector and for the jury's code review. | — |

Brand: dark, Inter, terracotta accent (`code/apps/shared/tuttie.css`), shared by all apps.

## Demo strategy: predictable, but real

The demo must never fail on stage, but the code behind it must really work.

**One app, not a demo app.** The wallet is the real product and works on its own for real
use. The demo is a *simulated run through that same app*: same pages, same components,
same backend. There is no separate demo page with its own look; whatever the audience sees
is what a real user would see.

- **Predictable:** the demo follows the storyline (`code/demo/`, issue #3): fixed user
  lines, fixed timing, and a voice agent whose lines we already know, so we play them
  directly instead of depending on live speech recognition.
- **Real:** every step of the demo calls the real functions: real registry lookups, real
  Ed25519 signatures and verification, real offers and negotiation, real signed approvals.
  The same code serves real use, so the code review sees the real system.
- **Rule:** the demo may fix *what is said or chosen*. It may never fake *verification*:
  a forged seal fails in the demo exactly as in real use.

## What exists today

Working and tested (see `readme.md`): the APS signing core, the registry, business nodes
with signed tools and their own A2A agent, the assistant's LLM tool loop with the trust
gate, signed phone approvals, bookings and the phone-first wallet. The current flow is "assistant goes
to the businesses"; the reverse marketplace, the wallet UI, voice, owner view, presentation
site and demo are the next work areas (`documentation/architecture.md`).
