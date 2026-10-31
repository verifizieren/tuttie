// The hotels as a deck of cards: swipe right to like, left to pass. Each card shows the hotel's
// photos (tap the left or right side to flip through them), its rating, its features as green
// or red icons and the price Tuttie's agents bargained, with the hotel's own offer crossed out.
// All of it comes from signed facts (assistant/cards.py). After the last card the wallet books
// the best liked deal. A gesture that starts mostly up or down scrolls the conversation instead.
import { useEffect, useRef, useState } from "react";
import FeatureIcon from "./FeatureIcon.jsx";
import { SealMarks } from "./Seals.jsx";

const AXIS_PX = 8;           // movement before a gesture is read as sideways (swipe) or up/down (scroll)
const DECIDE_PX = 90;        // dragged this far, the card is decided
const FLICK_SPEED = 0.5;     // px per ms that decides a shorter drag
const FLY_MS = 260;
const LEAN_PX = 150;         // drag distance at which Tuttie's eyes look all the way to the side

function Photos({ photos, name }) {
  const [shown, setShown] = useState(0);
  const [failed, setFailed] = useState(false);
  const flip = step => setShown(i => Math.min(photos.length - 1, Math.max(0, i + step)));
  return (
    <div className="swipe-photo">
      {photos.length > 0 && !failed
        ? <img src={photos[shown]} alt={name} draggable="false" onError={() => setFailed(true)} />
        : <div className="photo-missing" />}
      {photos.length > 1 && (
        <>
          {/* Taps on the left or right third flip the photo; drags still swipe the card. */}
          <button type="button" className="photo-prev" aria-label="Previous photo" data-tap onClick={() => flip(-1)} />
          <button type="button" className="photo-next" aria-label="Next photo" data-tap onClick={() => flip(1)} />
        </>
      )}
    </div>
  );
}

function HotelCard({ card, hotel, position, count, style, handlers, verdict, className = "" }) {
  const price = card.agreed_chf ?? card.price_chf;
  return (
    <article className={`swipe-card ${className}`} style={style} {...handlers}>
      <Photos photos={card.photos || []} name={card.name} />
      <div className="hotel-bars" role="img" aria-label={`Hotel ${position + 1} of ${count}`}>
        {Array.from({ length: count }, (_, i) => <i key={i} className={i === position ? "on" : ""} />)}
      </div>
      <div className="swipe-top">
        <SealMarks seals={hotel?.seals || []} tiers={[card.trust_tier]} />
        {card.rating && <span className="rating" aria-label={`rated ${card.rating.score} of 5`}>★ {card.rating.score}</span>}
      </div>
      {verdict && <span className={`stamp ${verdict}`}>{verdict === "like" ? "Like" : "Pass"}</span>}
      <div className="swipe-name">{card.name}</div>
      <div className="swipe-foot">
        <ul className="feature-icons">
          {card.features.map(f => (
            <li key={f.key} className={f.ok ? "yes" : "no"} title={f.label} aria-label={f.label}>
              <FeatureIcon name={f.key} />
            </li>
          ))}
        </ul>
        <div className="swipe-price">
          {card.agreed_chf != null && <s>CHF {card.price_chf}</s>}
          <b>CHF {price}</b>
        </div>
      </div>
    </article>
  );
}

/**
 * @param cards   the hotels to swipe (assistant/cards.py)
 * @param hotels  the wallet's hotel state, for the verified seals
 * @param onDone  (liked cards) => void, after the last card
 * @param onLean  (x in -1..1) => void while a card is dragged, 0 when it is let go (Tuttie's eyes follow)
 */
export default function Deck({ cards, hotels, onDone, onLean, commands = [] }) {
  const [index, setIndex] = useState(0);
  const [liked, setLiked] = useState([]);
  const [drag, setDrag] = useState(null);     // { dx, dy } while the finger moves the top card sideways
  const [flying, setFlying] = useState(null); // "like" | "pass" while the top card leaves
  const [nudge, setNudge] = useState(true);   // the first card shows once that it moves sideways
  const flight = useRef(null);
  const consumed = useRef(null);
  const gesture = useRef(null);               // { x, y, t, axis, scroller, scrollTop }

  useEffect(() => {
    const done = setTimeout(() => setNudge(false), 1600);
    return () => { clearTimeout(done); clearTimeout(flight.current); };
  }, []);

  function lean(x) {
    onLean?.(Math.max(-1, Math.min(1, x)));
  }

  function decide(verdict) {
    if (flying || index >= cards.length) return;
    setFlying(verdict);
    lean(verdict === "like" ? 1 : -1);
    flight.current = setTimeout(() => {
      const nextLiked = verdict === "like" ? [...liked, cards[index]] : liked;
      setLiked(nextLiked);
      setFlying(null);
      setDrag(null);
      setIndex(index + 1);
      lean(0);
      if (index + 1 >= cards.length && nextLiked.length) onDone(nextLiked);
    }, FLY_MS);
  }

  // Consume each live command once; leave the next command pending during a swipe.
  useEffect(() => {
    const command = commands.find(c => c.id > (consumed.current ?? -1));
    if (!command || flying || index >= cards.length) return;
    consumed.current = command.id;
    decide(command.verdict);
  }, [commands, flying, index]);

  const handlers = {
    onPointerDown: e => {
      if (flying) return;
      setNudge(false);
      const scroller = e.currentTarget.closest("[data-scroll]");
      gesture.current = { x: e.clientX, y: e.clientY, t: performance.now(), axis: null,
                          scroller, scrollTop: scroller?.scrollTop || 0 };
    },
    onPointerMove: e => {
      const g = gesture.current;
      if (!g) return;
      const dx = e.clientX - g.x, dy = e.clientY - g.y;
      if (!g.axis) {
        if (Math.hypot(dx, dy) < AXIS_PX) return;
        g.axis = Math.abs(dx) > Math.abs(dy) ? "x" : "y";
        try { e.currentTarget.setPointerCapture(e.pointerId); } catch { /* not every pointer can be captured */ }
      }
      if (g.axis === "y") {
        if (g.scroller) g.scroller.scrollTop = g.scrollTop - dy;  // up and down scroll the conversation
        return;
      }
      setDrag({ dx, dy: dy * 0.15 });
      lean(dx / LEAN_PX);
    },
    onPointerUp: e => {
      const g = gesture.current;
      gesture.current = null;
      if (!g || g.axis !== "x") return;
      const dx = e.clientX - g.x, speed = Math.abs(dx) / Math.max(16, performance.now() - g.t);
      if (Math.abs(dx) > DECIDE_PX || (Math.abs(dx) > 30 && speed > FLICK_SPEED)) decide(dx > 0 ? "like" : "pass");
      else { setDrag(null); lean(0); }
    },
    onPointerCancel: () => { gesture.current = null; setDrag(null); lean(0); },
  };

  if (index >= cards.length) {
    return liked.length ? null : (
      <div className="deck-empty">
        You passed on every hotel.
        <button type="button" onClick={() => { setIndex(0); setLiked([]); }}>See them again</button>
      </div>
    );
  }

  const dx = flying ? (flying === "like" ? 1 : -1) * 520 : drag?.dx || 0;
  const verdict = flying || (Math.abs(dx) > 30 ? (dx > 0 ? "like" : "pass") : null);
  const top = {
    transform: `translate(${dx}px, ${flying ? 40 : drag?.dy || 0}px) rotate(${dx / 18}deg)`,
    transition: drag && !flying ? "none" : `transform ${FLY_MS}ms var(--ease)`,
  };
  return (
    <section className="deck" data-hscroll>
      <div className="deck-stack">
        {index + 1 < cards.length && (
          <HotelCard key={cards[index + 1].node_id} card={cards[index + 1]} hotel={hotels[cards[index + 1].node_id]}
                     position={index + 1} count={cards.length} style={{ transform: "scale(.95) translateY(10px)", opacity: .6 }} handlers={{}} />
        )}
        <HotelCard key={cards[index].node_id} card={cards[index]} hotel={hotels[cards[index].node_id]}
                   style={nudge && index === 0 && !drag ? undefined : top} className={nudge && index === 0 && !drag ? "nudge" : ""}
                   position={index} count={cards.length} handlers={handlers} verdict={verdict} />
      </div>
      <div className="deck-count">{index + 1} of {cards.length}</div>
    </section>
  );
}
