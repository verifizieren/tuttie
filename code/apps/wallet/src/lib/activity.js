// Turns the assistant's timeline events (GET /events, format in documentation/formats.md)
// into what the wallet shows: the posting, the hotels, their offers, the negotiation, the
// approval and Tuttie's answer. Pure functions, so the view only ever renders `state`.

export const EMPTY = {
  phase: "idle",        // idle | thinking | posted | offers | negotiating | approval | done
  request: null,        // the public part of Tuttie's posting
  hotels: {},           // node_id -> { name, size, agent, tiers, status, offer, shortlisted, rounds, agreed }
  skipped: [],          // [{ name, reason }] not woken: untrusted or broken
  shortlistDone: false,
  approval: null,       // { id, amount, hotel, summary, seals } while the phone waits
  answer: "",
  thought: "",          // the latest reasoning summary title
};

const validTiers = seals => seals.filter(s => s.valid).map(s => s.tier);

function hotel(state, nodeId, name) {
  return state.hotels[nodeId] || { name, size: null, agent: null, tiers: [], status: "woken", offer: null,
                                   shortlisted: false, rounds: [], agreed: null };
}

function withHotel(state, nodeId, name, changes) {
  return { ...state, hotels: { ...state.hotels, [nodeId]: { ...hotel(state, nodeId, name), ...changes } } };
}

/** The next state after one event. Unknown events leave the state as it is. */
export function applyEvent(state, event) {
  const detail = event.detail || {};
  if (event.kind === "thinking") {
    const title = event.summary.match(/^\*\*(.+?)\*\*/);
    return { ...state, thought: title ? title[1] : state.thought, phase: state.phase === "idle" ? "thinking" : state.phase };
  }
  if (event.kind === "answer") return { ...state, answer: event.summary, phase: "done" };

  if (event.kind === "marketplace") {
    if (detail.phase === "posted") {
      const hotels = {};
      for (const [nodeId, info] of Object.entries(detail.invited || {})) {
        hotels[nodeId] = { ...hotel(state, nodeId, info.name), size: info.profile?.size || null, agent: info.agent,
                           tiers: [info.trust_tier], status: info.status || "woken" };
      }
      const skipped = Object.values(detail.skipped || {}).map(s => ({ name: s.name, reason: s.reason }));
      // A new posting starts a new run: earlier offers, approvals and answers no longer apply.
      return { ...EMPTY, phase: "posted", request: detail.request, hotels, skipped, thought: state.thought };
    }
    if (detail.phase === "offer" && event.node_id) {
      return { ...withHotel(state, event.node_id, event.node_name, {
        offer: detail.offer, tiers: validTiers(event.seals), status: "offered",
        size: detail.profile?.size || hotel(state, event.node_id).size,
      }), phase: "offers" };
    }
    if (detail.phase === "shortlist") {
      const ids = new Set(detail.shortlist || []);
      const hotels = Object.fromEntries(Object.entries(state.hotels).map(
        ([nodeId, h]) => [nodeId, { ...h, shortlisted: Boolean(h.offer && ids.has(h.offer.offer_id)) }]));
      return { ...state, hotels, shortlistDone: true };
    }
    return state;
  }

  // Negotiation rounds arrive as signed a2a replies whose payload is a counter or an agreement.
  if (event.kind === "a2a" && event.node_id && ["counter", "agreement"].includes(detail.payload?.type)) {
    const h = hotel(state, event.node_id, event.node_name);
    const step = { price: detail.payload.price_chf, final: Boolean(detail.payload.final), type: detail.payload.type };
    return { ...withHotel(state, event.node_id, event.node_name, {
      rounds: [...h.rounds, step],
      agreed: detail.payload.type === "agreement" ? detail.payload.price_chf : h.agreed,
      status: detail.payload.type === "agreement" ? "agreed" : "negotiating",
    }), phase: "negotiating" };
  }

  if (event.kind === "approval") {
    if (event.status === "pending") {
      return { ...state, phase: "approval", approval: { id: detail.approval_id, amount: detail.amount_chf,
        hotel: event.node_name, summary: event.summary, seals: event.seals } };
    }
    return { ...state, approval: null, phase: event.status === "approved" ? "booking" : "declined" };
  }
  return state;
}

/** A short line for the status under the eyes. */
export function statusLine(state) {
  const offers = Object.values(state.hotels).filter(h => h.offer).length;
  switch (state.phase) {
    case "thinking": return state.thought || "Thinking…";
    case "posted": return `Asked ${Object.keys(state.hotels).length} hotels…`;
    case "offers": return `${offers} offer${offers === 1 ? "" : "s"} in`;
    case "negotiating": return "Negotiating…";
    case "approval": return "Waiting for your approval";
    case "booking": return "Booking…";
    case "declined": return "You declined";
    default: return "";
  }
}

/** The face's expression for a phase (names from lib/face.js). */
export const EXPRESSION = {
  thinking: "skepticism", posted: "amazement", offers: "happiness", negotiating: "suspicion",
  approval: "pleading", booking: "neutral", declined: "sadness", done: "happiness",
};
