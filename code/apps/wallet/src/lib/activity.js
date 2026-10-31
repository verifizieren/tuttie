// Turns the assistant's timeline events (GET /events, format in documentation/formats.md)
// into what the wallet shows: one conversation as turns (what the user said, Tuttie's answer),
// plus what happened on the agent web in between: the posting, the hotels and their offers,
// the cards to swipe, the negotiation, the approval and the booking. Each turn has two
// progress lines that update in place: what Tuttie knows (context) and what it does (tools).
// Every request (typed or spoken) is a turn the server opens with a "turn" event; the events of
// its run carry its id (`event.turn`), so they always land in their own turn: a new request
// never overwrites an earlier answer or booking. Pure functions, so the view only ever renders `state`.

export const EMPTY = {
  id: null,             // this conversation, for the history on this device
  turns: [],            // [{ id, said, source, answer, mood, context, tool, booking }]; context/tool: { text, done } progress lines
  phase: "idle",        // idle | thinking | posted | offers | picking | negotiating | approval | booking | booked | done | declined
  request: null,        // the public part of Tuttie's posting
  marketTurn: null,     // the turn in which the posting happened
  hotels: {},           // node_id -> { name, size, agent, tiers, seals, uid, status, offer, shortlisted, rounds, agreed }
  skipped: [],          // [{ name, reason, tier }] not woken: untrusted or broken
  shortlistDone: false,
  cards: null,          // the hotels to swipe (assistant/cards.py), once the offers are in
  swipes: [],           // queued live commands; preserve rapid consecutive choices
  deck: null,           // { step, index, liked: [node_id] }: how far the user swiped these cards (kept on reload)
  picked: null,         // node ids the user liked
  approval: null,       // { id, amount, hotel, summary, seals, uid, offerMandate, terms } while the user decides
  booking: null,        // the latest { id, hotel, total, date, room, rate, extras, checked, seals, uid, payments }; each stays in its turn
  bookingTurn: null,
  answer: "",           // Tuttie's latest answer
  mood: "neutral",      // how it feels (assistant/agent.py MOODS)
  closing: null,        // the user said goodbye: "asked" (end_conversation), "ready" once Tuttie answered
};

const validTiers = seals => seals.filter(s => s.valid).map(s => s.tier);
const newId = () => `c-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`;

/** The turn events belong to: the first one still waiting for an answer, else the last. */
export function activeTurn(state) {
  const open = state.turns.findIndex(t => !t.answer);
  return open === -1 ? state.turns.length - 1 : open;
}

/** The turn an event belongs to: the one with its id, else (events without one) the active turn. */
export function turnOf(state, turnId) {
  const i = turnId ? state.turns.findIndex(t => t.id === turnId) : -1;
  return i === -1 ? activeTurn(state) : i;
}

/** A conversation that has ended: answered, nothing waiting for the user or still running. */
export const finished = state => Boolean(state.answer) && !state.approval && state.turns.every(t => t.answer);

/** The user said something: a new turn (and a new conversation if there is none). A turn
 *  typed here remembers the phase before it, in case sending it fails (`dropTurn`). */
export function startTurn(state, said, id = null, source = "text") {
  const turn = id ? { id, said, source } : { said, before: state.phase };
  return { ...state, id: state.id || newId(), turns: [...state.turns, turn], phase: "thinking", closing: null };
}

/** The newest message typed here that has no server turn yet and no answer, with these words. */
const unsent = (state, said) => state.turns.findLastIndex(t => !t.id && !t.answer && t.said === said);

/** POST /chat accepted a message as turn `id`: bind it now, so its events land in it even if the
 *  "turn" event is late or was missed. Never twice. */
export function bindTurn(state, said, id) {
  if (!id || state.turns.some(t => t.id === id)) return state;
  const i = unsent(state, said);
  if (i === -1) return state;
  return { ...state, turns: state.turns.map((t, n) => (n === i ? { ...t, id } : t)) };
}

/** Sending a message failed: the server never got it, so it is not a turn. Without this it would
 *  stay open forever and catch the events of later requests (see `activeTurn`). */
export function dropTurn(state, said) {
  const i = unsent(state, said);
  if (i === -1) return state;
  const turns = state.turns.filter((_, n) => n !== i);
  const open = turns.some(t => !t.answer);
  return { ...state, turns, phase: open ? state.phase : state.turns[i].before || (state.answer ? "done" : "idle") };
}

/** The server opened a turn ("turn" event): bind it to the message just sent from this wallet
 *  (same words, no id yet), or add it (a spoken request, or a reload). Never twice. */
function openTurn(state, { turn_id: id, said = "", source = "text" }) {
  if (!id || state.turns.some(t => t.id === id)) return state;
  const local = state.turns.findIndex(t => !t.id && !t.answer && t.said === said);
  if (local === -1) return startTurn(state, said, id, source);
  const turns = state.turns.map((t, n) => (n === local ? { ...t, id, source } : t));
  return { ...state, turns, phase: "thinking", closing: null };
}

/** Tuttie's answer without the timeline citations ([3]) or lines about ignored businesses. */
export const cleanAnswer = text => text.split("\n").filter(line => !/^\s*Ignored:/i.test(line)).join("\n")
  .replace(/\s*\[\d+\]/g, "").trim();

/** Events need a turn to belong to; a timeline without the user's messages gets an empty one. */
const withTurn = state => (state.turns.length ? state : { ...state, turns: [{ said: "" }] });

/** Update one progress line ("context" or "tool") of the turn the event belongs to. */
function progress(state, line, text, done = false, turnId = null) {
  const base = withTurn(state), i = turnOf(base, turnId);
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

function withAnswer(state, text, mood, turnId) {
  const base = withTurn(state), i = turnOf(base, turnId);
  // Tuttie has answered: nothing in this turn is still running, so its progress lines are done.
  const settle = line => (line ? { ...line, done: true } : line);
  const turns = base.turns.map((t, n) => (n === i ? { ...t, answer: text, mood, context: settle(t.context),
                                                       tool: settle(t.tool) } : t));
  // A late answer to an earlier turn never replaces the answer to a later one.
  const newest = turns.slice(i + 1).every(t => !t.answer);
  const waiting = turns.slice(i + 1).some(t => !t.answer);
  const closing = state.closing === "asked" ? "ready" : state.closing;
  if (!newest) return { ...base, turns, closing };
  return { ...base, turns, answer: text, mood, phase: waiting ? "thinking" : "done", closing };
}

/** The latest booking, kept both as `state.booking` and in the turn it was made in. */
function withBooking(state, booking) {
  const turns = state.turns.map((t, n) => (n === state.bookingTurn ? { ...t, booking } : t));
  return { ...state, turns, booking };
}

/** A charge paid after the booking (e.g. the city tax), from the hotel's signed receipt. */
function withPayment(state, receipt) {
  if (!state.booking) return state;
  const payment = { purpose: receipt.purpose, amount: receipt.amount_chf, paidWith: receipt.paid_with,
                    checked: receipt.checked || [] };
  return withBooking(state, { ...state.booking, payments: [...state.booking.payments, payment] });
}

/** The next state after one event. Unknown events leave the state as it is. */
export function applyEvent(state, event) {
  const detail = event.detail || {};
  const at = event.turn || null;  // the turn the event belongs to (documentation/formats.md)
  if (event.kind === "turn") return openTurn(state, detail);
  if (event.kind === "wallet" && detail.action === "swipe" && ["like", "pass"].includes(detail.verdict)) {
    if (!state.cards || state.picked || detail.cards_step !== state.cardsStep) return state;
    const swipe = { id: event.step, verdict: detail.verdict };
    if (state.swipes.some(s => s.id === swipe.id)) return state;
    return { ...state, swipes: [...state.swipes, swipe] };
  }
  if (event.kind === "thinking") return state.phase === "idle" ? { ...state, phase: "thinking" } : state;
  if (event.kind === "close") return { ...state, closing: "asked" };
  if (event.kind === "answer") return withAnswer(state, cleanAnswer(event.summary), detail.mood || "neutral", at);
  if (event.kind === "context") return progress(state, "context", event.summary, detail.phase === "found", at);
  if (event.kind === "payment" && detail.payload?.status === "paid") {
    return withPayment(progress(state, "tool", `Booked · ${detail.payload.purpose} paid`, true, at), detail.payload);
  }

  if (event.kind === "marketplace") {
    if (detail.phase === "posted") {
      const hotels = {};
      for (const [nodeId, info] of Object.entries(detail.invited || {})) {
        hotels[nodeId] = { ...hotel({ hotels: {} }, nodeId, info.name), size: info.profile?.size || null, agent: info.agent,
                           tiers: [info.trust_tier], status: info.status || "woken" };
      }
      const skipped = Object.values(detail.skipped || {}).map(s => ({ name: s.name, reason: s.reason, tier: s.trust_tier }));
      // A new posting replaces the last one's market, offers and picks in this conversation; an
      // earlier booking stays in its own turn.
      const base = progress(state, "tool", `Asked ${Object.keys(hotels).length} hotels`, false, at);
      return { ...base, phase: "posted", request: detail.request, marketTurn: turnOf(base, at), hotels, skipped,
               shortlistDone: false, cards: null, cardsStep: null, swipes: [], deck: null, picked: null, approval: null, booking: null, bookingTurn: null };
    }
    if (detail.phase === "offer" && event.node_id) {
      const next = withHotel(state, event.node_id, event.node_name, {
        offer: detail.offer, tiers: validTiers(event.seals), seals: event.seals, uid: event.uid, status: "offered",
        size: detail.profile?.size || hotel(state, event.node_id).size,
      });
      const n = offerCount(next);
      return { ...progress(next, "tool", `${n} offer${n === 1 ? "" : "s"} in · checking seals`, false, at), phase: "offers" };
    }
    if (detail.phase === "shortlist") {
      const ids = new Set(detail.shortlist || []);
      const hotels = Object.fromEntries(Object.entries(state.hotels).map(
        ([nodeId, h]) => [nodeId, { ...h, shortlisted: Boolean(h.offer && ids.has(h.offer.offer_id)) }]));
      return { ...progress(state, "tool", "Comparing offers", false, at), hotels, shortlistDone: true };
    }
    if (detail.phase === "cards") {
      const n = (detail.cards || []).length;
      return { ...progress(state, "tool", `${n} hotel${n === 1 ? "" : "s"} for you`, true, at),
               cards: detail.cards || [], cardsStep: event.step, swipes: [], deck: null, phase: "picking" };
    }
    return state;
  }

  // Negotiation rounds arrive as signed a2a replies whose payload is a counter or an agreement.
  if (event.kind === "a2a" && event.node_id && ["counter", "agreement"].includes(detail.payload?.type)) {
    const h = hotel(state, event.node_id, event.node_name);
    const step = { price: detail.payload.price_chf, final: Boolean(detail.payload.final), type: detail.payload.type };
    const trail = [h.offer?.price_chf, ...h.rounds.map(r => r.price), step.price].filter((p, i, all) => p != null && (i === 0 || p !== all[i - 1]))
      .map(p => `CHF ${p}`).join(" → ");
    const line = step.type === "agreement" ? `Agreed with ${h.name} · CHF ${step.price}` : `Bargaining with ${h.name} · ${trail}`;
    const cards = step.type === "agreement" && state.cards
      ? state.cards.map(c => c.node_id === event.node_id ? { ...c, agreed_chf: step.price } : c)
      : state.cards;
    return { ...withHotel(progress(state, "tool", line, false, at), event.node_id, event.node_name, {
      rounds: [...h.rounds, step],
      agreed: detail.payload.type === "agreement" ? detail.payload.price_chf : h.agreed,
      status: detail.payload.type === "agreement" ? "agreed" : "negotiating",
    }), cards, phase: "negotiating" };
  }

  // The hotel's signed confirmation, with the checks its action gate passed.
  if (event.kind === "a2t" && detail.payload?.tool === "book" && detail.payload.status === "confirmed") {
    const b = detail.payload;
    const base = progress(state, "tool", `Booked · ${detail.payload.booking_id}`, true, at);
    return withBooking({ ...base, phase: "booked", bookingTurn: turnOf(base, at) },
                       { id: b.booking_id, hotel: b.hotel, total: b.total_chf, date: b.date, room: b.room_type,
                         rate: b.rate || null, extras: b.extras || [], checked: b.checked || [], seals: event.seals, uid: event.uid,
                         payments: [] });
  }

  if (event.kind === "approval") {
    if (event.status === "pending") {
      return { ...progress(state, "tool", "Waiting for your approval", false, at), phase: "approval", approval: { id: detail.approval_id, amount: detail.amount_chf,
        hotel: event.node_name, summary: event.summary, seals: event.seals, uid: event.uid,
        offerMandate: detail.offer_mandate || null, terms: detail.terms || null } };
    }
    const approved = event.status === "approved";
    return { ...progress(state, "tool", approved ? "Booking…" : "You declined", !approved, at), approval: null,
             phase: approved ? "booking" : "declined" };
  }
  return state;
}

/** The user swiped a card of the deck shown now: remember how far, so a reload continues there. */
export const withDeck = (state, { index, liked }) =>
  (state.cards ? { ...state, deck: { step: state.cardsStep, index, liked } } : state);

/** Where the deck starts: the saved position if it belongs to these cards and some are left. */
export function deckStart(state) {
  const deck = state.deck;
  if (!deck || !state.cards || deck.step !== state.cardsStep || deck.index >= state.cards.length) return null;
  return { index: deck.index, liked: deck.liked };
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
