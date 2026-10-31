// Turns the assistant's timeline events (GET /events, format in documentation/formats.md)
// into what the wallet shows: one conversation as turns (what the user said, Tuttie's answer),
// plus what happened on the agent web in between: the posting, the hotels and their offers,
// the cards to swipe, the negotiation, the approval and the booking. Each turn has two
// progress lines that update in place: what Tuttie knows (context) and what it does (tools).
// Pure functions, so the view only ever renders `state`.

export const EMPTY = {
  id: null,             // this conversation, for the history on this device
  turns: [],            // [{ said, answer, mood, context, tool }]; context/tool: { text, done } progress lines
  phase: "idle",        // idle | thinking | posted | offers | picking | negotiating | approval | booking | booked | done | declined
  request: null,        // the public part of Tuttie's posting
  marketTurn: null,     // the turn in which the posting happened
  hotels: {},           // node_id -> { name, size, agent, tiers, seals, uid, status, offer, shortlisted, rounds, agreed }
  skipped: [],          // [{ name, reason, tier }] not woken: untrusted or broken
  shortlistDone: false,
  cards: null,          // the hotels to swipe (assistant/cards.py), once the offers are in
  picked: null,         // node ids the user liked
  approval: null,       // { id, amount, hotel, summary, seals, uid, offerMandate } while the user decides
  booking: null,        // { id, hotel, total, date, room, extras, checked, seals, uid, payments } once confirmed
  bookingTurn: null,
  answer: "",           // Tuttie's latest answer
  mood: "neutral",      // how it feels (assistant/agent.py MOODS)
};

const validTiers = seals => seals.filter(s => s.valid).map(s => s.tier);
const newId = () => `c-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`;

/** The turn events belong to: the first one still waiting for an answer, else the last. */
export function activeTurn(state) {
  const open = state.turns.findIndex(t => !t.answer);
  return open === -1 ? state.turns.length - 1 : open;
}

/** A conversation that has ended: answered, nothing waiting for the user or still running. */
export const finished = state => Boolean(state.answer) && !state.approval && state.turns.every(t => t.answer);

/** The user said something: a new turn (and a new conversation if there is none). */
export function startTurn(state, said) {
  return { ...state, id: state.id || newId(), turns: [...state.turns, { said }], phase: "thinking" };
}

/** Tuttie's answer without the timeline citations ([3]) or lines about ignored businesses. */
export const cleanAnswer = text => text.split("\n").filter(line => !/^\s*Ignored:/i.test(line)).join("\n")
  .replace(/\s*\[\d+\]/g, "").trim();

/** Events need a turn to belong to; a timeline without the user's messages gets an empty one. */
const withTurn = state => (state.turns.length ? state : { ...state, turns: [{ said: "" }] });

/** Update one progress line ("context" or "tool") of the turn events belong to. */
function progress(state, line, text, done = false) {
  const base = withTurn(state), i = activeTurn(base);
  return { ...base, turns: base.turns.map((t, n) => (n === i ? { ...t, [line]: { text, done } } : t)) };
}

const offerCount = state => Object.values(state.hotels).filter(h => h.offer).length;

function hotel(state, nodeId, name) {
  return state.hotels[nodeId] || { name, size: null, agent: null, tiers: [], seals: [], uid: null, status: "woken",
                                   offer: null, shortlisted: false, rounds: [], agreed: null };
}

function withHotel(state, nodeId, name, changes) {
  return { ...state, hotels: { ...state.hotels, [nodeId]: { ...hotel(state, nodeId, name), ...changes } } };
}

function withAnswer(state, text, mood) {
  const base = withTurn(state), i = activeTurn(base);
  // Tuttie has answered: nothing in this turn is still running, so its progress lines are done.
  const settle = line => (line ? { ...line, done: true } : line);
  const turns = base.turns.map((t, n) => (n === i ? { ...t, answer: text, mood, context: settle(t.context),
                                                       tool: settle(t.tool) } : t));
  return { ...base, turns, answer: text, mood, phase: "done" };
}

/** A charge paid after the booking (e.g. the city tax), from the hotel's signed receipt. */
function withPayment(state, receipt) {
  if (!state.booking) return state;
  const payment = { purpose: receipt.purpose, amount: receipt.amount_chf, paidWith: receipt.paid_with,
                    checked: receipt.checked || [] };
  return { ...state, booking: { ...state.booking, payments: [...state.booking.payments, payment] } };
}

/** The next state after one event. Unknown events leave the state as it is. */
export function applyEvent(state, event) {
  const detail = event.detail || {};
  if (event.kind === "thinking") return state.phase === "idle" ? { ...state, phase: "thinking" } : state;
  if (event.kind === "answer") return withAnswer(state, cleanAnswer(event.summary), detail.mood || "neutral");
  if (event.kind === "context") return progress(state, "context", event.summary, detail.phase === "found");
  if (event.kind === "payment" && detail.payload?.status === "paid") {
    return withPayment(progress(state, "tool", `Booked · ${detail.payload.purpose} paid`, true), detail.payload);
  }

  if (event.kind === "marketplace") {
    if (detail.phase === "posted") {
      const hotels = {};
      for (const [nodeId, info] of Object.entries(detail.invited || {})) {
        hotels[nodeId] = { ...hotel(state, nodeId, info.name), size: info.profile?.size || null, agent: info.agent,
                           tiers: [info.trust_tier], status: info.status || "woken" };
      }
      const skipped = Object.values(detail.skipped || {}).map(s => ({ name: s.name, reason: s.reason, tier: s.trust_tier }));
      // A new posting replaces the last one's market, offers, picks and booking in this conversation.
      const base = progress(state, "tool", `Asked ${Object.keys(hotels).length} hotels`);
      return { ...base, phase: "posted", request: detail.request, marketTurn: activeTurn(base), hotels, skipped,
               shortlistDone: false, cards: null, picked: null, approval: null, booking: null, bookingTurn: null };
    }
    if (detail.phase === "offer" && event.node_id) {
      const next = withHotel(state, event.node_id, event.node_name, {
        offer: detail.offer, tiers: validTiers(event.seals), seals: event.seals, uid: event.uid, status: "offered",
        size: detail.profile?.size || hotel(state, event.node_id).size,
      });
      const n = offerCount(next);
      return { ...progress(next, "tool", `${n} offer${n === 1 ? "" : "s"} in · checking seals`), phase: "offers" };
    }
    if (detail.phase === "shortlist") {
      const ids = new Set(detail.shortlist || []);
      const hotels = Object.fromEntries(Object.entries(state.hotels).map(
        ([nodeId, h]) => [nodeId, { ...h, shortlisted: Boolean(h.offer && ids.has(h.offer.offer_id)) }]));
      return { ...progress(state, "tool", "Comparing offers"), hotels, shortlistDone: true };
    }
    if (detail.phase === "cards") {
      const n = (detail.cards || []).length;
      return { ...progress(state, "tool", `${n} hotel${n === 1 ? "" : "s"} for you`, true),
               cards: detail.cards || [], phase: "picking" };
    }
    return state;
  }

  // Negotiation rounds arrive as signed a2a replies whose payload is a counter or an agreement.
  if (event.kind === "a2a" && event.node_id && ["counter", "agreement"].includes(detail.payload?.type)) {
    const h = hotel(state, event.node_id, event.node_name);
    const step = { price: detail.payload.price_chf, final: Boolean(detail.payload.final), type: detail.payload.type };
    const trail = [h.offer?.price_chf, ...h.rounds.map(r => r.price), step.price].filter(p => p != null)
      .map(p => `CHF ${p}`).join(" → ");
    const line = step.type === "agreement" ? `Agreed with ${h.name} · CHF ${step.price}` : `Bargaining with ${h.name} · ${trail}`;
    return { ...withHotel(progress(state, "tool", line), event.node_id, event.node_name, {
      rounds: [...h.rounds, step],
      agreed: detail.payload.type === "agreement" ? detail.payload.price_chf : h.agreed,
      status: detail.payload.type === "agreement" ? "agreed" : "negotiating",
    }), phase: "negotiating" };
  }

  // The hotel's signed confirmation, with the checks its action gate passed.
  if (event.kind === "a2t" && detail.payload?.tool === "book" && detail.payload.status === "confirmed") {
    const b = detail.payload;
    const base = progress(state, "tool", `Booked · ${detail.payload.booking_id}`, true);
    return { ...base, phase: "booked", bookingTurn: activeTurn(base),
             booking: { id: b.booking_id, hotel: b.hotel, total: b.total_chf, date: b.date, room: b.room_type,
                        extras: b.extras || [], checked: b.checked || [], seals: event.seals, uid: event.uid,
                        payments: [] } };
  }

  if (event.kind === "approval") {
    if (event.status === "pending") {
      return { ...progress(state, "tool", "Waiting for your approval"), phase: "approval", approval: { id: detail.approval_id, amount: detail.amount_chf,
        hotel: event.node_name, summary: event.summary, seals: event.seals, uid: event.uid,
        offerMandate: detail.offer_mandate || null } };
    }
    const approved = event.status === "approved";
    return { ...progress(state, "tool", approved ? "Booking…" : "You declined", !approved), approval: null,
             phase: approved ? "booking" : "declined" };
  }
  return state;
}

/** What Tuttie is doing right now, for the line under its eyes: the step still running, or
 *  "" when it only listens or thinks (the eyes show that). */
export function currentTask(state) {
  if (state.approval) return "Waiting for your approval";
  if (state.phase === "booking") return "Booking…";
  const turn = state.turns[activeTurn(state)];
  if (!turn || turn.answer) return "";
  const running = [turn.tool, turn.context].find(line => line && !line.done);
  return running ? running.text : "";
}

/** While Tuttie works it does not hold one face: it moves through these looks, each with a
 *  glance (x, y in -1..1), like someone thinking. Names from lib/face.js. */
export const THINKING = [
  { name: "skepticism", look: [-.6, -.5] },
  { name: "confusion", look: [.5, -.4] },
  { name: "suspicion", look: [0, .2] },
  { name: "neutral", look: [.7, -.6] },
  { name: "skepticism", look: [-.3, .3] },
];

/** The face for each answer mood, so even small talk shows on Tuttie's face. */
export const MOOD = {
  happy: "happiness", excited: "excitement", proud: "happiness", thoughtful: "skepticism",
  surprised: "surprise", confused: "confusion", sad: "sadness", sorry: "guilt", worried: "fear",
  neutral: "neutral",
};

/** While Tuttie waits for the user it listens: its eyes stay open and attentive, glance a little
 *  and nod now and then (y > 0 looks down). Names from lib/face.js. */
export const LISTENING = [
  { name: "listening", look: [0, 0] },
  { name: "attentive", look: [.18, -.08] },
  { name: "listening", look: [0, .3] },      // a small nod
  { name: "listening", look: [-.15, -.05] },
  { name: "attentive", look: [0, 0] },
];

/** While the user swipes the hotel cards, Tuttie looks down at them with them. */
export const WATCHING = [
  { name: "listening", look: [0, .55] },
  { name: "attentive", look: [.12, .6] },
  { name: "listening", look: [-.1, .5] },
];

/** Phases in which Tuttie is busy and the face cycles through THINKING. */
export const BUSY = new Set(["thinking", "posted", "negotiating", "booking"]);

/** The face's expression for a phase (names from lib/face.js). */
export const EXPRESSION = {
  thinking: "skepticism", posted: "amazement", offers: "happiness", picking: "happiness", negotiating: "suspicion",
  approval: "pleading", booking: "neutral", booked: "happiness", declined: "sadness", done: "happiness",
};
