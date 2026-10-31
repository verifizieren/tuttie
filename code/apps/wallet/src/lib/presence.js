// What Tuttie is doing right now, as one signal for its eyes to animate from.
//
// The wallet knows many things at once: the card's mode, the conversation's phase (lib/activity.js),
// whether Tuttie or the user is talking (voice levels from LiveKit), a waiting approval, an error.
// This module folds them into one PRESENCE the animation can follow, so the eyes never have to
// know where a signal came from. No React and no drawing here: pure functions plus a tiny
// event hub, so it can be tested with `npm test` and used by any face (lib/face.js or a new one).
//
// Three kinds of signals (all delivered through createPresence().subscribe):
//   { type: "state",  state, since, detail }  what Tuttie is doing, changes rarely (see STATES)
//   { type: "levels", speaking, hearing }     voice loudness 0..1, ~20 times a second
//   { type: "cue",    name, detail }          a one-off moment to react to (see CUES)

/** Every state, in the order they win when several are true (first wins). */
export const STATES = [
  "asleep",       // the card is closed: eyes shut
  "listening",    // the user is talking right now (microphone level)
  "speaking",     // Tuttie is talking right now (its voice level): lip-sync-like pulsing
  "typing",       // the user is typing a message (keyboard open)
  "error",        // Tuttie cannot be reached
  "waiting",      // an approval waits for the user's tap / Face ID
  "watching",     // the user swipes the hotel cards (detail.lean: -1..1 while a card is dragged)
  "negotiating",  // bargaining with hotels (detail.hotel, detail.price: the latest round)
  "searching",    // out on the agent web: posting, hotels answering, checking seals
  "booking",      // the approved booking and payment are running
  "thinking",     // Tuttie (the LLM) is working out what to do
  "done",         // an answer arrived (detail.mood: happy, sorry, ... from the assistant)
  "idle",         // awake, nothing happening: ready to listen
];

/** One-off moments, emitted once each (detail in brackets). */
export const CUES = [
  "wake", "sleep", "tap", "new_chat",           // the user opened / closed / tapped Tuttie, started over
  "user_said",                                  // a new message from the user (text)
  "posted",                                     // the request went out to the hotels (hotels: count)
  "scam_blocked",                               // a hotel was not asked: broken or untrusted (name, tier)
  "offer",                                      // a hotel sent a signed offer (hotel, price, tiers)
  "counter",                                    // a bargaining round (hotel, price, final)
  "agreement",                                  // a hotel agreed to a price (hotel, price)
  "cards",                                      // hotels to swipe are ready (count)
  "approval_requested", "approved", "declined", // the phone moment (amount, hotel)
  "booked", "paid",                             // the hotel confirmed / a charge was paid (hotel, total / purpose, amount, paidWith)
  "answer",                                     // Tuttie's answer arrived (mood)
];

// A voice counts as talking above ON and keeps counting until it has been below OFF for HOLD_MS,
// so the gaps between words do not make the eyes flicker between states.
export const VOICE = { on: 0.08, off: 0.04, holdMs: 350 };

const PHASE_STATE = {
  thinking: "thinking", posted: "searching", offers: "searching", picking: "watching",
  negotiating: "negotiating", approval: "waiting", booking: "booking", booked: "booking",
  done: "done", declined: "done",
};

/**
 * Whether Tuttie and the user are talking, with hysteresis. Pure: pass the previous result back in.
 * @param prev   the last result (or undefined)
 * @param levels { speaking, hearing } 0..1 (Tuttie's voice, the user's microphone)
 * @param now    milliseconds (performance.now())
 * @returns { speaking: bool, hearing: bool, speakingAt, hearingAt } (…At: last time above "off")
 */
export function voiceActivity(prev, { speaking = 0, hearing = 0 }, now) {
  const one = (active, level, lastAt) => {
    if (level >= VOICE.on) return [true, now];
    if (level >= VOICE.off) return [active, active ? now : lastAt];
    return [active && now - lastAt < VOICE.holdMs, lastAt];
  };
  const [speakingOn, speakingAt] = one(prev?.speaking ?? false, speaking, prev?.speakingAt ?? -Infinity);
  const [hearingOn, hearingAt] = one(prev?.hearing ?? false, hearing, prev?.hearingAt ?? -Infinity);
  return { speaking: speakingOn, hearing: hearingOn, speakingAt, hearingAt };
}

/** The latest bargaining round across the hotels, for the "negotiating" detail. */
function latestRound(agent) {
  let best = null;
  for (const h of Object.values(agent.hotels || {})) {
    const round = h.rounds?.[h.rounds.length - 1];
    if (round && (!best || h.rounds.length >= best.rounds)) best = { hotel: h.name, price: round.price, rounds: h.rounds.length };
  }
  return best;
}

/**
 * What Tuttie is doing, from everything the wallet knows. Pure.
 * @param inputs { mode: "closed"|"voice"|"typing", agent: activity state, voice: voiceActivity(),
 *                 error: string, lean: number (-1..1, 0 = no card dragged) }
 * @returns { state, detail }
 */
export function presenceOf({ mode = "closed", agent = {}, voice = {}, error = "", lean = 0 }) {
  const phase = agent.phase || "idle";
  if (mode === "closed") return { state: "asleep", detail: {} };
  if (voice.hearing && mode === "voice") return { state: "listening", detail: { phase } };
  if (voice.speaking && mode === "voice") return { state: "speaking", detail: { phase, mood: agent.mood } };
  if (mode === "typing") return { state: "typing", detail: { phase } };
  if (error) return { state: "error", detail: { message: error } };
  if (agent.approval) return { state: "waiting", detail: { amount: agent.approval.amount, hotel: agent.approval.hotel } };
  const state = PHASE_STATE[phase] || "idle";
  if (state === "watching") return { state, detail: { lean, count: (agent.cards || []).length } };
  if (state === "negotiating") return { state, detail: latestRound(agent) || {} };
  if (state === "done") return { state, detail: { mood: phase === "declined" ? "sad" : agent.mood || "neutral" } };
  return { state, detail: { phase } };
}

const offerCount = agent => Object.values(agent.hotels || {}).filter(h => h.offer).length;

/**
 * The one-off moments between two conversation states (lib/activity.js), in the order they
 * happened. Pure: compare the state before and after an event.
 * @returns [{ name, detail }]
 */
export function cuesBetween(before = {}, after = {}) {
  const cues = [];
  const cue = (name, detail = {}) => cues.push({ name, detail });
  // Only real words: an event without a message first opens an empty turn (lib/activity.js).
  const said = (after.turns?.length || 0) > (before.turns?.length || 0) && after.turns.at(-1).said;
  if (said) cue("user_said", { text: said });
  if (after.request && after.request !== before.request) {
    cue("posted", { hotels: Object.keys(after.hotels || {}).length });
    for (const s of after.skipped || []) cue("scam_blocked", { name: s.name, tier: s.tier });
  }
  for (const [id, h] of Object.entries(after.hotels || {})) {
    const old = before.hotels?.[id] || {};
    if (h.offer && h.offer !== old.offer) cue("offer", { hotel: h.name, price: h.offer.price_chf, tiers: h.tiers || [] });
    for (const round of (h.rounds || []).slice(old.rounds?.length || 0)) {
      cue(round.type === "agreement" ? "agreement" : "counter", { hotel: h.name, price: round.price, final: round.final });
    }
  }
  if (after.cards && after.cards !== before.cards) cue("cards", { count: after.cards.length });
  if (after.approval && after.approval.id !== before.approval?.id) {
    cue("approval_requested", { amount: after.approval.amount, hotel: after.approval.hotel });
  }
  if (before.approval && !after.approval) {
    if (after.phase === "declined") cue("declined", { hotel: before.approval.hotel });
    else if (after.phase === "booking" || after.phase === "booked") cue("approved", { amount: before.approval.amount, hotel: before.approval.hotel });
  }
  if (after.booking && after.booking.id !== before.booking?.id) cue("booked", { hotel: after.booking.hotel, total: after.booking.total });
  const paid = after.booking?.payments || [], paidBefore = before.booking?.id === after.booking?.id ? before.booking?.payments || [] : [];
  for (const p of paid.slice(paidBefore.length)) cue("paid", { purpose: p.purpose, amount: p.amount, paidWith: p.paidWith });
  if (after.answer && after.answer !== before.answer) cue("answer", { mood: after.mood || "neutral" });
  return cues;
}

/**
 * A small hub the wallet feeds and the eyes listen to.
 * @param now  clock in ms (tests pass a fake one)
 * @returns { update(inputs), levels(speaking, hearing), cue(name, detail), current(), subscribe(fn) → unsubscribe }
 */
export function createPresence(now = () => performance.now()) {
  const listeners = new Set();
  let inputs = { mode: "closed", agent: {}, error: "", lean: 0 };
  let voice = voiceActivity(undefined, {}, now());
  let current = { state: "asleep", since: now(), detail: {} };
  const emit = event => listeners.forEach(fn => fn(event));

  function recompute() {
    const next = presenceOf({ ...inputs, voice });
    const same = next.state === current.state && JSON.stringify(next.detail) === JSON.stringify(current.detail);
    if (same) return;
    current = { ...next, since: next.state === current.state ? current.since : now() };
    emit({ type: "state", ...current });
  }

  return {
    /** New wallet inputs (any subset of { mode, agent, error, lean }). */
    update(changes) {
      inputs = { ...inputs, ...changes };
      recompute();
    },
    /** Voice loudness, 0..1 each (Tuttie's voice, the user's microphone); call ~20×/s. */
    levels(speaking, hearing) {
      voice = voiceActivity(voice, { speaking, hearing }, now());
      emit({ type: "levels", speaking, hearing });
      recompute();
    },
    /** A one-off moment (one of CUES). */
    cue(name, detail = {}) {
      emit({ type: "cue", name, detail });
    },
    /** The current { state, since, detail }. */
    current: () => current,
    /** Listen to every signal; returns the function that stops listening. */
    subscribe(fn) {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
  };
}
