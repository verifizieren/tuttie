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
  decided: null,        // { id, status } of the last approval the server closed (approved, declined, expired)
  booking: null,        // the latest { id, hotel, total, date, room, rate, extras, checked, seals, uid, payments }; each stays in its turn
  bookingTurn: null,
  answer: "",           // Tuttie's latest answer
  mood: "neutral",      // how it feels (assistant/agent.py MOODS)
  closing: null,        // the user said goodbye: "asked" (end_conversation), "ready" once Tuttie answered
};

const validTiers = (seals = []) => sealsOf(seals).filter(s => s.valid).map(s => s.tier);

/** A value the wallet shows as text: a string or a number, anything else (an object, null) is "". */
export const plain = value => (typeof value === "string" ? value
  : typeof value === "number" && Number.isFinite(value) ? String(value) : "");

/** An event's seals as a list of seal objects with a plain issuer and tier; anything else in an
 *  event (null, a word) is dropped. */
export const sealsOf = seals => (Array.isArray(seals) ? seals : [])
  .filter(s => s && typeof s === "object" && !Array.isArray(s))
  .map(s => ({ ...s, issuer: plain(s.issuer), tier: plain(s.tier), valid: s.valid === true }));

/** A booking approval as the sheet shows it: only plain text and numbers, never an object
 *  (a hotel's signed facts flow into it, and the sheet must always be able to render). */
const amountOf = value => (typeof value === "number" && Number.isFinite(value) ? value : plain(value));

export function approvalOf(event, detail) {
  const terms = detail.terms && typeof detail.terms === "object" ? detail.terms : null;
  const offer = detail.offer_mandate && typeof detail.offer_mandate === "object" ? detail.offer_mandate : null;
  return {
    id: plain(detail.approval_id), amount: amountOf(detail.amount_chf), hotel: plain(event.node_name),
    summary: plain(event.summary), seals: sealsOf(event.seals), uid: plain(event.uid) || null,
    offerMandate: offer && { purpose: plain(offer.purpose) || "the next charge", price_chf: amountOf(offer.price_chf) },
    terms: terms && { room_type: plain(terms.room_type), date: plain(terms.date), rate: plain(terms.rate) },
  };
}
/** A hotel card (assistant/cards.py) as the deck shows it: the shown fields are plain text,
 *  numbers or null, never an object (a hotel's own text flows into a card, and an object in
 *  React's output breaks the whole chat view). Other fields stay as they came. */
const number = value => (typeof value === "number" && Number.isFinite(value) ? value : null);
export function cardOf(card) {
  const rated = number(card.rating?.score);
  const score = rated !== null && rated >= 0 && rated <= 5 ? rated : null;  // a score out of 5
  return {
    ...card,
    node_id: plain(card.node_id), name: plain(card.name), agent: plain(card.agent), about: plain(card.about),
    trust_tier: plain(card.trust_tier), price_chf: number(card.price_chf), agreed_chf: number(card.agreed_chf),
    over_budget_chf: number(card.over_budget_chf),
    rating: score === null ? null : { ...card.rating, score },
    features: (Array.isArray(card.features) ? card.features : []).filter(f => f && typeof f === "object")
      .map(f => ({ ...f, key: plain(f.key), ok: f.ok === true, label: plain(f.label) })),
    photos: (Array.isArray(card.photos) ? card.photos : []).filter(p => typeof p === "string"),
  };
}
const cardsOf = cards => (Array.isArray(cards) ? cards : []).filter(c => c && typeof c === "object" && !Array.isArray(c)).map(cardOf);

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

// Notes the model put in square brackets, cleaned the same way as the voice (voice/agent.py
// spoken(); shared cases in code/tests/fixtures/answer_notes.json). Only what carries nothing to
// say goes: citations ([3], [3, 4]), a few labels ([confirmed]), booking and receipt ids, node
// ids, approval, offer and mandate ids (also alone in parentheses: "Rheinblick (ch.basel.x)").
// Any other note may be a fact (a fee, "cancelled"), so it stays without its brackets.
// Markdown links keep their text. All patterns run in linear time.
const LINK = /\[([^[\]\n]*)\]\(([^()\n]*)\)/g;
const NOTE = /\[([^[\]\n]{0,60})\]/g;
const CITATION = /^\d+(?:\s*,\s*\d+)*$/;
// A bracketed number that is a price, not a citation: with a thousands separator ("[1,280]"), or
// right after a currency ("CHF [128]") or before one ("[90] CHF"). Decimals are no citation anyway.
const THOUSANDS = /^[0-9]{1,3}(?:[,'’][0-9]{3})+$/;
const CURRENCY_BEFORE = /(?:\b(?:CHF|francs?|EUR|USD|GBP|Fr\.)|[€$£])[ \t]*$/i;
const CURRENCY_AFTER = /^[ \t]*(?:(?:CHF|francs?|EUR|USD|GBP)\b|[€$£])/i;
const LABEL = /^(?:confirmed|verified|signed|sources?)$/i;
// Node ids have one shape (data/nodes/*.json): ch.<area>.<name>; hosts like de.sbb.ch stay.
const NODE_ID_TOKEN = "ch\\.[a-z]{2,20}\\.[a-z0-9]{1,30}(?:-[a-z0-9]{1,30}){0,6}";
const NODE_ID = new RegExp(`^${NODE_ID_TOKEN}$`, "i");
// Approval, mandate, request and offer ids (assistant/approvals.py, aps/mandate.py,
// marketplace/client.py, node/agent.py), in any case; an offer's hex tail has a digit.
const REF_TOKEN = "(?:ap|md|rq)-[0-9a-f]{8}|of-[a-z0-9-]{1,60}-(?=[a-f]*\\d)[0-9a-f]{6}";
const REF = new RegExp(`^(?:${REF_TOKEN})$`, "i");
const INTERNAL = `(?:${NODE_ID_TOKEN}|${REF_TOKEN})`;
const IDS = `${INTERNAL}(?:\\s*[,;]\\s*${INTERNAL})*`;
const PAREN_IDS = new RegExp(`\\(\\s*${IDS}\\s*\\)`, "gi");               // "(ch.basel.x)": all of it goes
const LEAD_IDS = new RegExp(`(?<=\\()\\s*${IDS}\\s*[,;]\\s*`, "gi");        // "(ch.basel.x, CHF 128)": "(CHF 128)"
const TRAIL_IDS = new RegExp(`(?<=\\S)\\s*[,;]\\s*${IDS}\\s*(?=\\))`, "gi"); // "(CHF 128, ch.basel.x)": "(CHF 128)"
const ID = /,?\s*(?:(?:receipt|booking)(?:\s+id)?\s*)?\b(?:BK|RC)-[0-9A-F]{6}\b/gi;
const WEB_ADDRESS = /^\s*(?:https?:\/\/|www\.)\S*\s*$/i;
const GONE = "\u0000";  // where a note was taken out: the spaces around it are tidied there only
// "Ignored: <business>." when it starts a line (also as "1.", "•", "- **Ignored:**") or a sentence:
// dropped up to the end of its sentence. A lowercase "was ignored: ..." inside a sentence stays.
const IGNORED_LINE = /^[ \t]*(?:(?:[-*•>#]|\d+[.)])[ \t]*)?[*_]*Ignored:[^\n]*?(?:[.!?](?=[ \t]|$)[ \t]*|$)/;
const IGNORED_SENTENCE = /(?<=[.!?])[ \t]+[*_]*Ignored:[^\n]*?(?:[.!?](?=[ \t]|$)|$)/g;
const LINES = /\r\n?|\n|\u2028|\u2029/;  // line breaks, split the same way as the voice
const EMPTY_ANSWER = "Done.";  // an answer that cleans to nothing

function link(all, label, target) {
  const text = label.trim();
  if (text && !CITATION.test(text)) return text;
  return !target.trim() || WEB_ADDRESS.test(target) ? GONE : `(${target})`;
}

function note(all, inner, offset, text) {
  const words = inner.replace(ID, "").replace(/^[\s,;]+|[\s,;]+$/g, "");
  const price = THOUSANDS.test(words) || (/^[0-9]+$/.test(words) && (
    CURRENCY_BEFORE.test(text.slice(Math.max(0, offset - 12), offset))
    || CURRENCY_AFTER.test(text.slice(offset + all.length, offset + all.length + 12))));
  if (!words || (CITATION.test(words) && !price) || LABEL.test(words) || NODE_ID.test(words) || REF.test(words) || /^ignored:/i.test(words)) return GONE;
  return (offset > 0 && /[\p{L}\p{N}]/u.test(text[offset - 1]) ? " " : "") + words;
}

export function withoutNotes(value) {
  const raw = String(value ?? "");
  let text = raw.replace(/\r\n?/g, "\n").replace(LINK, link).replace(PAREN_IDS, GONE)
    .replace(LEAD_IDS, "").replace(TRAIL_IDS, "");
  for (let i = 0; i < 3; i++) text = text.replace(NOTE, note);  // nested: "[[3]]" leaves "[]" after one pass
  text = text.replace(/\u0000(?:[ \t]*\u0000)+/g, GONE)       // notes in a row count as one
    .replace(/[ \t]?\u0000(?=[.,;:!?)\]'"’]|$)/gm, "").replace(/^\u0000[ \t]?/gm, "")
    .replace(/[ \t]?\u0000[ \t]?/g, " ");
  text = text.split(LINES).map(line => [line, line.replace(IGNORED_LINE, "").replace(IGNORED_SENTENCE, "")])
    .filter(([line, cut]) => cut.replace(/[ \t\-*_#>•]/g, "") || !line.trim()).map(([, cut]) => cut).join("\n");
  // A non-empty answer never cleans to nothing (nor to raw links or forged names): a neutral line.
  return !text.trim() && raw.trim() ? EMPTY_ANSWER : text;
}

/** Tuttie's answer without bracketed notes or lines starting with "Ignored:" (see above). */
export const cleanAnswer = text => withoutNotes(text).trim();

/** Simple markdown (**bold**, *italic*, _italic_, `code`) as plain text, for a line that shows
 *  no formatting (the note under the hotel cards). Underscores inside words stay. */
export const plainMarkdown = text => String(text ?? "")
  .replace(/\*\*([^*\n]+?)\*\*/g, "$1")
  .replace(/(^|[^\w*])\*(?=\S)([^*\n]*?\S)\*(?![\w*])/g, "$1$2")
  .replace(/(^|[^\w])_(?=\S)([^_\n]*?\S)_(?!\w)/g, "$1$2")
  .replace(/`([^`\n]+)`/g, "$1");

/** The hotel cards are swiped only while the user still chooses: not once a hotel was liked, and
 *  not once a booking is under way (the user named a hotel instead of swiping): then the
 *  approval and the booked block take their place. */
export const choosing = state => Boolean(state.cards && !state.picked && !state.approval && !state.booking
  && state.phase !== "booking");  // approved: the hotel is booking it, the confirmation follows

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
        offer: detail.offer, tiers: validTiers(event.seals), seals: sealsOf(event.seals), uid: event.uid, status: "offered",
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
      const cards = cardsOf(detail.cards);
      const n = cards.length;
      return { ...progress(state, "tool", `${n} hotel${n === 1 ? "" : "s"} for you`, true, at),
               cards, cardsStep: event.step, swipes: [], deck: null, phase: "picking" };
    }
    return state;
  }

  // Negotiation rounds arrive as signed a2a replies whose payload is a counter or an agreement.
  // A round whose price is not a number (a hotel's own reply) changes nothing: it would break
  // the card that shows it.
  if (event.kind === "a2a" && event.node_id && ["counter", "agreement"].includes(detail.payload?.type)
      && number(detail.payload.price_chf) !== null) {
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
                         rate: b.rate || null, extras: b.extras || [], checked: b.checked || [], seals: sealsOf(event.seals), uid: event.uid,
                         payments: [] });
  }

  if (event.kind === "approval") {
    if (event.status === "pending") {
      // A booking under way means the hotel was chosen, also when another tab (or the voice)
      // chose it: these cards are done here too, so a swipe here never starts a second booking.
      const chosen = state.cards && !state.picked
        ? { picked: state.cards.some(c => c.node_id === event.node_id) ? [event.node_id] : [] } : {};
      return { ...progress(state, "tool", "Waiting for your approval", false, at), ...chosen, phase: "approval",
               approval: approvalOf(event, detail) };
    }
    // the approval id is inside the signed decision (aps/approval.py sign_decision)
    const decided = { id: plain(detail.decision?.approval_id ?? detail.approval_id), status: plain(event.status) };
    // The end of an older approval while a newer one waits: only remembered (its sheet may still
    // be finishing), the newer approval stays.
    if (decided.id && state.approval && decided.id !== state.approval.id) return { ...state, decided };
    // Only a decision the user made is named; any other end (e.g. expired) just closes it.
    const approved = event.status === "approved";
    const line = approved ? "Booking…" : event.status === "declined" ? "You declined" : "Approval closed";
    return { ...progress(state, "tool", line, !approved, at), approval: null, decided,
             phase: approved ? "booking" : "declined" };
  }
  return state;
}

/** The user swiped a card of the deck shown now: remember how far, so a reload continues there. */
export const withDeck = (state, { index, liked }) =>
  (state.cards ? { ...state, deck: { step: state.cardsStep, index, liked } } : state);

/** A saved deck position in the shape the deck needs: a whole card index from 0 and the liked
 *  hotels' node ids. A stored copy can be anything (an old version, a hand-edited browser). */
export const validDeck = deck => Boolean(deck) && typeof deck === "object" && Number.isInteger(deck.index)
  && deck.index >= 0 && Array.isArray(deck.liked) && deck.liked.every(id => typeof id === "string");

/** Where the deck starts: the saved position if it belongs to these cards and some are left. */
export function deckStart(state) {
  const deck = state.deck;
  if (!validDeck(deck) || !state.cards || deck.step !== state.cardsStep || deck.index >= state.cards.length) return null;
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
