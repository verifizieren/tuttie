// One conversation under Tuttie's eyes, turn by turn: what the user said, what Tuttie did on
// the agent web (the posting, the hotels and their offers, the cards to pick favourites from,
// the negotiation, the booking) and Tuttie's answer. Tapping a hotel shows who vouches for it.
// The same view shows an archived conversation from the history (readOnly).
import { useEffect, useRef, useState } from "react";
import BookingCard from "./BookingCard.jsx";
import Picker from "./Picker.jsx";
import { SealList, SealMarks } from "./Seals.jsx";

function RequestCard({ request }) {
  const { constraints, tags } = request;
  const needs = [...constraints.requirements, ...tags.map(t => t.replace("-", " "))];
  return (
    <div className="request">
      <div className="request-title">Looking for a {request.category} · {constraints.date}</div>
      {needs.length > 0 && <div className="request-needs">{needs.join(" · ")}</div>}
      <div className="private">Your budget stays private</div>
    </div>
  );
}

/** The price column: the offer, the bargaining trail, or the agreed price. */
function Price({ hotel }) {
  if (hotel.agreed) {
    return <span className="price"><s>{hotel.offer?.price_chf}</s> <b>CHF {hotel.agreed}</b></span>;
  }
  if (hotel.rounds.length) {
    const last = hotel.rounds[hotel.rounds.length - 1];
    return <span className="price">{hotel.offer?.price_chf} → <b>{last.price}</b>{last.final ? " final" : ""}</span>;
  }
  if (hotel.offer) return <span className="price"><b>CHF {hotel.offer.price_chf}</b></span>;
  const waiting = { interested: "preparing offer…", declined: "no offer", woken: "asked…" };
  return <span className="price muted">{waiting[hotel.status] || hotel.status}</span>;
}

function HotelRow({ hotel, overBudget, open, onToggle }) {
  const classes = ["hotel", hotel.shortlisted && "picked", hotel.agreed && "agreed", overBudget && "out", open && "open"];
  const includes = hotel.offer?.includes || [];
  return (
    <div className={classes.filter(Boolean).join(" ")}>
      <button type="button" className="hotel-line" onClick={onToggle} aria-expanded={open}>
        <SealMarks seals={hotel.seals} tiers={hotel.tiers} />
        <span className="hotel-name">
          {hotel.name}
          <small>{[hotel.size, overBudget && "over budget", hotel.agreed && "agreed"].filter(Boolean).join(" · ")}</small>
        </span>
        <Price hotel={hotel} />
      </button>
      {open && (
        <div className="hotel-more">
          {includes.length > 0 && <div className="includes">Includes {includes.join(", ")}</div>}
          <SealList seals={hotel.seals} uid={hotel.uid} />
        </div>
      )}
    </div>
  );
}

/** A business Tuttie never asked: a forged seal (red) or no seal at all (grey). */
function SkippedRow({ business }) {
  const forged = business.tier === "broken";
  return (
    <div className={`hotel skipped ${forged ? "forged" : "untrusted"}`}>
      <span className="hotel-line">
        <span className="seal-x" aria-hidden="true">{forged ? "!" : "?"}</span>
        <span className="hotel-name">
          <s>{business.name}</s>
          <small>{forged ? "Forged seal · never asked" : "No valid seal · never asked"}</small>
        </span>
      </span>
    </div>
  );
}

/** **bold** inside a line. */
function Inline({ text }) {
  return text.split(/(\*\*[^*]+\*\*)/).map((part, i) =>
    part.startsWith("**") ? <b key={i}>{part.slice(2, -2)}</b> : <span key={i}>{part}</span>);
}

/** Tuttie's answer as a highlighted bubble: paragraphs, "- " lines as a list, **bold** kept. */
function Answer({ text }) {
  const blocks = [];
  for (const line of text.split("\n").map(l => l.trim())) {
    if (!line) continue;
    const item = line.match(/^[-•*]\s+(.*)/);
    if (item) {
      if (blocks.at(-1)?.list) blocks.at(-1).list.push(item[1]);
      else blocks.push({ list: [item[1]] });
    } else {
      blocks.push({ text: line });
    }
  }
  return (
    <div className="bubble tuttie">
      {blocks.map((b, i) => (b.list
        ? <ul key={i}>{b.list.map((t, j) => <li key={j}><Inline text={t} /></li>)}</ul>
        : <p key={i}><Inline text={b.text} /></p>))}
    </div>
  );
}

/** Shortlisted hotels first, then the other offers by price, then hotels still thinking. */
function order(hotels) {
  const rank = h => (h.shortlisted ? 0 : h.offer ? 1 : 2);
  return Object.entries(hotels).sort(([, a], [, b]) =>
    rank(a) - rank(b) || (a.agreed ?? a.offer?.price_chf ?? 1e9) - (b.agreed ?? b.offer?.price_chf ?? 1e9));
}

/** What happened on the market in this conversation: the request, then the cards or the hotels. */
function Market({ state, readOnly, onPick }) {
  const [openId, setOpenId] = useState(null);
  const picking = state.cards && !state.picked;
  // Once the user picked, the hotels they chose show the negotiation; before the cards, all offers come in.
  const shown = order(state.hotels).filter(([nodeId]) => !state.picked || state.picked.includes(nodeId));
  return (
    <>
      <RequestCard request={state.request} />
      {state.cards && (picking || readOnly)
        ? <Picker cards={state.cards} hotels={state.hotels} picked={readOnly ? state.picked || [] : state.picked}
                  onPick={onPick} />
        : shown.map(([nodeId, hotel]) => (
            <HotelRow key={nodeId} hotel={hotel} overBudget={state.shortlistDone && hotel.offer && !hotel.shortlisted}
                      open={openId === nodeId} onToggle={() => setOpenId(openId === nodeId ? null : nodeId)} />
          ))}
      {state.skipped.map((business, i) => <SkippedRow key={i} business={business} />)}
    </>
  );
}

/**
 * @param state     the conversation (lib/activity.js)
 * @param readOnly  an archived conversation from the history: nothing can be picked
 * @param onPick    (favourite cards) => void
 */
export default function Activity({ state, readOnly = false, onPick }) {
  const box = useRef(null);
  const last = state.turns.at(-1);
  // New content comes last; bring it into view when it arrives (not for archived conversations).
  // The cards to pick from are shown from their top, so the photos and prices are in view.
  useEffect(() => {
    if (readOnly || !box.current) return;
    const picker = state.cards && !state.picked && box.current.querySelector(".picker");
    const top = picker ? picker.offsetTop - 8 : box.current.scrollHeight;
    box.current.scrollTo({ top, behavior: "smooth" });
  }, [readOnly, state.turns.length, last?.answer, state.cards, state.booking, state.picked]);

  if (!state.turns.length && !state.request) return null;
  return (
    <div className={`activity${readOnly ? " archived" : ""}`} ref={box} data-scroll>
      {state.turns.map((turn, i) => (
        <div className="turn" key={i}>
          {turn.said && <div className="bubble user">{turn.said}</div>}
          {i === state.marketTurn && state.request && <Market state={state} readOnly={readOnly} onPick={onPick} />}
          {i === state.bookingTurn && state.booking && <BookingCard booking={state.booking} />}
          {turn.answer && <Answer text={turn.answer} />}
        </div>
      ))}
    </div>
  );
}
