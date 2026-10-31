// One conversation under Tuttie's eyes, turn by turn: what the user said, two progress lines
// (what Tuttie knows, what it does), the hotel cards to swipe, the negotiation with the liked
// hotels, the booking and Tuttie's answer. Tapping a hotel shows who vouches for it. The same
// view shows an archived conversation from the history (readOnly).
import { useEffect, useRef, useState } from "react";
import BookingCard from "./BookingCard.jsx";
import Deck from "./Deck.jsx";
import { SealList, SealMarks } from "./Seals.jsx";

/** The turn's progress: a context line, then a tool line joined to it. Each updates in place. */
function Steps({ turn }) {
  const lines = [turn.context, turn.tool].filter(Boolean);
  if (!lines.length) return null;
  return (
    <ol className="steps">
      {lines.map((line, i) => (
        <li key={i} className={line.done ? "done" : "active"}><i className="dot" /><span>{line.text}</span></li>
      ))}
    </ol>
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

/** A business with a forged seal: Tuttie never asked it. One quiet red line. */
function Forged({ business }) {
  return (
    <div className="forged-line"><span className="seal-x" aria-hidden="true">!</span>
      <s>{business.name}</s> forged seal, never asked
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

/** What happened on the market: the forged business, then the cards to swipe or the liked hotels. */
function Market({ state, readOnly, onPick }) {
  const [openId, setOpenId] = useState(null);
  const swiping = state.cards && !state.picked && !readOnly;
  // Once the user liked some, those show the negotiation; the progress line covers everything before.
  const liked = order(state.hotels).filter(([nodeId]) => state.picked?.includes(nodeId));
  return (
    <>
      {state.skipped.filter(b => b.tier === "broken").map((business, i) => <Forged key={i} business={business} />)}
      {swiping && <Deck cards={state.cards} hotels={state.hotels} onDone={onPick} />}
      {liked.map(([nodeId, hotel]) => (
        <HotelRow key={nodeId} hotel={hotel} overBudget={false}
                  open={openId === nodeId} onToggle={() => setOpenId(openId === nodeId ? null : nodeId)} />
      ))}
    </>
  );
}

/**
 * @param state     the conversation (lib/activity.js)
 * @param readOnly  an archived conversation from the history: nothing can be picked
 * @param onPick    (liked cards) => void
 */
export default function Activity({ state, readOnly = false, onPick }) {
  const box = useRef(null);
  const last = state.turns.at(-1);
  // New content comes last; bring it into view when it arrives (not for archived conversations).
  // The cards to swipe are shown from their top, so the whole card is in view.
  useEffect(() => {
    if (readOnly || !box.current) return;
    const deck = state.cards && !state.picked && box.current.querySelector(".deck");
    const top = deck ? deck.offsetTop - 8 : box.current.scrollHeight;
    box.current.scrollTo({ top, behavior: "smooth" });
  }, [readOnly, state.turns.length, last?.answer, state.cards, state.booking, state.picked]);

  if (!state.turns.length && !state.request) return null;
  return (
    <div className={`activity${readOnly ? " archived" : ""}`} ref={box} data-scroll>
      {state.turns.map((turn, i) => (
        <div className="turn" key={i}>
          {turn.said && <div className="bubble user">{turn.said}</div>}
          <Steps turn={turn} />
          {i === state.marketTurn && state.request && <Market state={state} readOnly={readOnly} onPick={onPick} />}
          {i === state.bookingTurn && state.booking && <BookingCard booking={state.booking} />}
          {turn.answer && <Answer text={turn.answer} />}
        </div>
      ))}
    </div>
  );
}
