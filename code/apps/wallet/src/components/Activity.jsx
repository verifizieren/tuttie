// One conversation under Tuttie's eyes, turn by turn: two progress lines (what Tuttie knows,
// what it does), the hotel cards to swipe, the chosen hotel, the booking and Tuttie's answer.
// The user's own words are not repeated, except in an earlier conversation from the history.
// Tapping a hotel shows who vouches for it.
import { useEffect, useRef, useState } from "react";
import BookingCard from "./BookingCard.jsx";
import Deck from "./Deck.jsx";
import { deckStart, plainMarkdown } from "../lib/activity.js";
import { SealList, SealMarks } from "./Seals.jsx";

/** The turn's progress: a context line, then a tool line joined to it. Each updates in place.
 *  `latest` is the line that finished last in the whole conversation: its dot is green. */
function Steps({ turn, latest }) {
  const lines = [turn.context, turn.tool].filter(Boolean);
  if (!lines.length) return null;
  return (
    <ol className="steps">
      {lines.map((line, i) => (
        <li key={i} className={line.done ? (line === latest ? "done latest" : "done") : "active"}>
          <i className="dot" /><span>{line.text}</span>
        </li>
      ))}
    </ol>
  );
}

/** The price column: the offer, the bargaining trail, or the agreed price. */
function Price({ hotel }) {
  if (hotel.agreed) {
    return <span className="price"><s>CHF {hotel.offer?.price_chf}</s> <b>CHF {hotel.agreed}</b></span>;
  }
  if (hotel.rounds.length) {
    const last = hotel.rounds[hotel.rounds.length - 1];
    return <span className="price">CHF {hotel.offer?.price_chf} → <b>CHF {last.price}</b>{last.final ? " quoted" : ""}</span>;
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
          {(overBudget || hotel.agreed) && <small>{overBudget ? "over budget" : "agreed"}</small>}
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


/** **bold** inside a line. */
function Inline({ text }) {
  return text.split(/(\*\*[^*]+\*\*)/).map((part, i) =>
    part.startsWith("**") ? <b key={i}>{part.slice(2, -2)}</b> : <span key={i}>{part}</span>);
}

/** Tuttie's answer as a highlighted bubble: paragraphs, "- " lines as a list, **bold** kept.
 *  While Tuttie is still saying it (`spoken`), only the words said so far are shown. */
function Answer({ text, spoken }) {
  if (spoken != null) {
    return <div className="bubble tuttie speaking"><p>{spoken}<span className="caret" aria-hidden="true" /></p></div>;
  }
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

/** What happened on the market: the hotel the user chose (the cards to swipe are shown on
 *  their own, see Activity). Businesses with forged or missing seals are not shown at all:
 *  Tuttie never asked them. */
function Market({ state }) {
  const [openId, setOpenId] = useState(null);
  // The chosen hotel, until the booking card replaces it.
  const liked = state.booking ? [] : order(state.hotels).filter(([nodeId]) => state.picked?.includes(nodeId));
  return (
    <>
      {liked.map(([nodeId, hotel]) => (
        <HotelRow key={nodeId} hotel={hotel} overBudget={false}
                  open={openId === nodeId} onToggle={() => setOpenId(openId === nodeId ? null : nodeId)} />
      ))}
    </>
  );
}

/**
 * @param state     the conversation (lib/activity.js)
 * @param readOnly  an earlier conversation from the history: nothing to swipe
 * @param onPick    (liked cards) => void
 * @param onLean    (x in -1..1) => void while a card is dragged
 * @param onDeck    ({ index, liked }) => void after each swiped card (kept for a reload)
 * @param reveal    { answer, text } while Tuttie speaks its latest answer
 */
export default function Activity({ state, readOnly = false, onPick, onLean, onDeck, reveal = null }) {
  const box = useRef(null);
  const last = state.turns.at(-1);
  const swiping = Boolean(state.cards && !state.picked && !readOnly && onPick);
  // New content comes last; bring it into view when it arrives.
  useEffect(() => {
    if (readOnly || swiping || !box.current) return;
    box.current.scrollTo({ top: box.current.scrollHeight, behavior: "smooth" });
  }, [readOnly, swiping, state.turns.length, last?.answer, state.booking, state.picked]);

  if (!state.turns.length && !state.request) return null;
  // The cards to swipe get the card's space to themselves, in place: no list behind them, only
  // Tuttie's newest answer since the cards came (its recommendation, or the answer to a question
  // asked meanwhile), shown as it is spoken while it is spoken.
  if (swiping) {
    const note = state.turns.slice(state.marketTurn ?? 0).findLast(t => t.answer)?.answer;
    const spoken = note && reveal?.answer === note ? reveal.text : null;
    return (
      <div className="activity swiping">
        <Deck key={state.cardsStep} cards={state.cards} hotels={state.hotels} onDone={onPick} onLean={onLean} commands={state.swipes}
              start={deckStart(state)} onProgress={onDeck} />
        {note && <p className="deck-note">{plainMarkdown(spoken ?? note)}</p>}
      </div>
    );
  }
  // Live progress has one context line and one tool line, even after follow-ups/searches.
  // Keep the per-turn account only in history.
  const liveProgress = state.turns.reduce((lines, turn) => ({
    context: turn.context || lines.context, tool: turn.tool || lines.tool,
  }), {});
  const latest = state.turns.flatMap(t => [t.context, t.tool]).filter(line => line?.done).at(-1);
  // What Tuttie did stays (steps, the chosen hotel, every booking in its own turn); of what it
  // said, only its current answer (the newest one) is shown, until the next answer replaces it.
  // The history (readOnly) keeps every answer.
  const current = state.turns.findLastIndex(t => t.answer);
  return (
    <div className="activity" ref={box} data-scroll>
      {!readOnly && <Steps turn={liveProgress} latest={latest} />}
      {state.turns.map((turn, i) => {
        const showMarket = i === state.marketTurn && state.request && !state.booking && state.picked?.length;
        // Archived chats from before bookings were kept per turn only have `state.booking`.
        const booking = turn.booking || (i === state.bookingTurn && state.booking);
        const showAnswer = turn.answer && (readOnly || i === current);
        // Empty historical turns still take a flex gap; omit them from the live layout.
        if (!readOnly && !showMarket && !booking && !showAnswer) return null;
        return <div className="turn" key={turn.id || i}>
          {readOnly && turn.said && <div className="bubble user">{turn.said}</div>}
          {readOnly && <Steps turn={turn} latest={latest} />}
          {showMarket && <Market state={state} />}
          {booking && <BookingCard booking={booking} />}
          {showAnswer && (
            <Answer text={turn.answer} spoken={reveal?.answer === turn.answer ? reveal.text : null} />
          )}
        </div>;
      })}
    </div>
  );
}
