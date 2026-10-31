// Tests for Tuttie's presence (lib/presence.js): `npm test` (Node's own test runner, no packages).
import assert from "node:assert/strict";
import { test } from "node:test";
import { applyEvent, EMPTY, startTurn } from "./activity.js";
import { CUES, createPresence, cuesBetween, presenceOf, STATES, VOICE, voiceActivity } from "./presence.js";

const awake = { mode: "voice", agent: EMPTY, voice: {} };

test("a closed card is asleep, whatever else happens", () => {
  const busy = { ...EMPTY, phase: "negotiating", approval: { amount: 128 } };
  assert.equal(presenceOf({ mode: "closed", agent: busy, voice: { speaking: true } }).state, "asleep");
});

test("each phase of the conversation has its state", () => {
  const states = Object.fromEntries(["idle", "thinking", "posted", "offers", "picking", "negotiating", "booking",
    "booked", "done", "declined"].map(phase => [phase, presenceOf({ ...awake, agent: { ...EMPTY, phase } }).state]));
  assert.deepEqual(states, {
    idle: "idle", thinking: "thinking", posted: "searching", offers: "searching", picking: "watching",
    negotiating: "negotiating", booking: "booking", booked: "booking", done: "done", declined: "done",
  });
  for (const state of Object.values(states)) assert.ok(STATES.includes(state), state);
});

test("voice wins over the phase: the user talking first, then Tuttie talking", () => {
  const agent = { ...EMPTY, phase: "negotiating" };
  assert.equal(presenceOf({ mode: "voice", agent, voice: { speaking: true, hearing: true } }).state, "listening");
  assert.equal(presenceOf({ mode: "voice", agent, voice: { speaking: true } }).state, "speaking");
  assert.equal(presenceOf({ mode: "typing", agent, voice: { speaking: true } }).state, "typing");  // voice is off while typing
});

test("waiting for the user's approval and errors win over the phase", () => {
  const agent = { ...EMPTY, phase: "approval", approval: { amount: 128, hotel: "Gästehaus am Rhein" } };
  assert.deepEqual(presenceOf({ ...awake, agent }), { state: "waiting", detail: { amount: 128, hotel: "Gästehaus am Rhein" } });
  assert.equal(presenceOf({ ...awake, agent, error: "Tuttie is unreachable right now" }).state, "error");
});

test("details: the latest bargaining round, the dragged card, the answer's mood", () => {
  const hotels = { a: { name: "Gästehaus am Rhein", rounds: [{ price: 131 }, { price: 130 }] }, b: { name: "Alpina", rounds: [{ price: 235 }] } };
  assert.deepEqual(presenceOf({ ...awake, agent: { ...EMPTY, phase: "negotiating", hotels } }).detail,
                   { hotel: "Gästehaus am Rhein", price: 130, rounds: 2 });
  assert.deepEqual(presenceOf({ ...awake, agent: { ...EMPTY, phase: "picking", cards: [1, 2] }, lean: -0.4 }).detail,
                   { lean: -0.4, count: 2 });
  assert.equal(presenceOf({ ...awake, agent: { ...EMPTY, phase: "done", mood: "happy" } }).detail.mood, "happy");
  assert.equal(presenceOf({ ...awake, agent: { ...EMPTY, phase: "declined", mood: "happy" } }).detail.mood, "sad");
});

test("talking holds through short pauses between words, then stops", () => {
  let v = voiceActivity(undefined, { speaking: 0.5 }, 0);
  assert.equal(v.speaking, true);
  v = voiceActivity(v, { speaking: 0 }, 200);              // a pause between words
  assert.equal(v.speaking, true);
  v = voiceActivity(v, { speaking: 0 }, VOICE.holdMs + 10);  // really quiet now
  assert.equal(v.speaking, false);
  v = voiceActivity(v, { speaking: (VOICE.on + VOICE.off) / 2 }, 1000);  // in between: not enough to start
  assert.equal(v.speaking, false);
  v = voiceActivity(v, { hearing: 0.3 }, 1100);
  assert.deepEqual([v.speaking, v.hearing], [false, true]);
});

// The pitch story as the wallet folds it, step by step (event formats from documentation/formats.md).
const seals = [{ issuer: "handelsregister-bs", tier: "gold", valid: true }];
const story = [
  { kind: "marketplace", detail: { phase: "posted", request: { category: "hotel" },
    invited: { g: { name: "Gästehaus am Rhein", trust_tier: "gold" } },
    skipped: { c: { name: "basel-cheap-hotels", reason: "forged seal", trust_tier: "broken" } } } },
  { kind: "marketplace", node_id: "g", node_name: "Gästehaus am Rhein", seals,
    detail: { phase: "offer", offer: { offer_id: "of-1", price_chf: 135 } } },
  { kind: "a2a", node_id: "g", node_name: "Gästehaus am Rhein", detail: { payload: { type: "counter", price_chf: 131 } } },
  { kind: "a2a", node_id: "g", node_name: "Gästehaus am Rhein", detail: { payload: { type: "agreement", price_chf: 128 } } },
  { kind: "approval", status: "pending", node_name: "Gästehaus am Rhein", seals, detail: { approval_id: "ap-1", amount_chf: 128 } },
  { kind: "approval", status: "approved", node_name: "Gästehaus am Rhein", seals, detail: {} },
  { kind: "a2t", seals, detail: { payload: { tool: "book", status: "confirmed", booking_id: "BK-1", hotel: "Gästehaus am Rhein", total_chf: 128 } } },
  { kind: "payment", detail: { payload: { status: "paid", purpose: "city tax", amount_chf: 4, paid_with: "mandate" } } },
  { kind: "answer", summary: "Booked.", detail: { mood: "happy" } },
];

test("the pitch story gives each moment once, in order", () => {
  let state = startTurn(EMPTY, "quiet hotel in Basel, with my dog");
  const names = cuesBetween(EMPTY, state).map(c => c.name);
  for (const event of story) {
    const next = applyEvent(state, event);
    names.push(...cuesBetween(state, next).map(c => c.name));
    state = next;
  }
  assert.deepEqual(names, ["user_said", "posted", "scam_blocked", "offer", "counter", "agreement",
                           "approval_requested", "approved", "booked", "paid", "answer"]);
  for (const name of names) assert.ok(CUES.includes(name), name);
});

test("cue details carry what the eyes may want to show", () => {
  const posted = applyEvent(EMPTY, story[0]);
  assert.deepEqual(cuesBetween(EMPTY, posted)[1], { name: "scam_blocked", detail: { name: "basel-cheap-hotels", tier: "broken" } });
  const agreed = story.slice(0, 4).reduce(applyEvent, EMPTY);
  assert.deepEqual(cuesBetween(story.slice(0, 3).reduce(applyEvent, EMPTY), agreed),
                   [{ name: "agreement", detail: { hotel: "Gästehaus am Rhein", price: 128, final: false } }]);
});

test("a declined approval gives 'declined', not 'approved'", () => {
  const waiting = story.slice(0, 5).reduce(applyEvent, EMPTY);
  const declined = applyEvent(waiting, { kind: "approval", status: "declined", detail: {} });
  assert.deepEqual(cuesBetween(waiting, declined).map(c => c.name), ["declined"]);
});

test("the hub sends state changes once, levels always, and cues as given", () => {
  let clock = 0;
  const presence = createPresence(() => clock);
  const seen = [];
  const stop = presence.subscribe(e => seen.push(e.type === "state" ? `state:${e.state}` : e.type === "cue" ? `cue:${e.name}` : "levels"));
  presence.update({ mode: "voice" });
  presence.update({ mode: "voice" });                 // nothing changed: no event
  presence.update({ agent: { ...EMPTY, phase: "thinking" } });
  clock = 100; presence.levels(0.6, 0);              // Tuttie starts talking
  clock = 150; presence.levels(0, 0);                // a short pause: still speaking
  clock = 600; presence.levels(0, 0);                // quiet long enough
  presence.cue("tap");
  stop();
  presence.cue("tap");                               // nobody listens any more
  assert.deepEqual(seen, ["state:idle", "state:thinking", "levels", "state:speaking", "levels", "levels", "state:thinking", "cue:tap"]);
  assert.equal(presence.current().state, "thinking");
  assert.equal(presence.current().since, 600);
});
