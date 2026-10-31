// The hotels as a deck of cards: swipe right to like, left to pass. Each card shows the rating,
// the hotel's features as green or red icons and the price, all built by Tuttie from signed
// facts (assistant/cards.py). After the last card, the liked hotels go to Tuttie, which
// negotiates with them and books the best deal (the user approves as usual).
import { useRef, useState } from "react";
import FeatureIcon from "./FeatureIcon.jsx";
import { SealMarks } from "./Seals.jsx";

const DECIDE_PX = 90;        // dragged this far, the card is decided
const FLICK_SPEED = 0.5;     // px per ms that decides a shorter drag
const FLY_MS = 260;

/** A calm drawn scene per hotel, used until the hotel has a photo (public/hotels/<node_id>.jpg). */
function Illustration({ name }) {
  const hue = [...name].reduce((h, c) => (h * 31 + c.charCodeAt(0)) % 360, 7);
  return (
    <svg className="illustration" viewBox="0 0 320 160" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
      <defs>
        <linearGradient id={`sky-${hue}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={`hsl(${hue} 45% 32%)`} />
          <stop offset="1" stopColor={`hsl(${(hue + 30) % 360} 40% 16%)`} />
        </linearGradient>
      </defs>
      <rect width="320" height="160" fill={`url(#sky-${hue})`} />
      <circle cx="168" cy="34" r="14" fill="rgba(255,236,210,.5)" />
      <path d="M0 122 L40 80 h40 v-22 l22 -18 22 18 v22 h34 v-34 h48 v34 h30 l22 -26 22 26 h40 V160 H0z"
            fill="rgba(8,8,11,.55)" />
      <g fill="rgba(255,226,170,.75)">
        <rect x="88" y="72" width="6" height="8" rx="1" /><rect x="110" y="72" width="6" height="8" rx="1" />
        <rect x="168" y="68" width="6" height="8" rx="1" /><rect x="186" y="82" width="6" height="8" rx="1" />
        <rect x="200" y="68" width="6" height="8" rx="1" />
      </g>
      <path d="M0 134 q40 -8 80 0 t80 0 t80 0 t80 0 V160 H0z" fill="rgba(120,170,220,.25)" />
    </svg>
  );
}

function Photo({ nodeId, name }) {
  const [failed, setFailed] = useState(false);
  return (
    <div className="swipe-photo">
      <Illustration name={name} />
      {!failed && <img src={`hotels/${nodeId}.jpg`} alt="" draggable="false" onError={() => setFailed(true)} />}
    </div>
  );
}

function Rating({ rating }) {
  if (!rating) return null;
  return <span className="rating" aria-label={`rated ${rating.score} of 5 by ${rating.reviews} guests`}>★ {rating.score}</span>;
}

function HotelCard({ card, hotel, style, handlers, verdict }) {
  return (
    <article className="swipe-card" style={style} {...handlers}>
      <Photo nodeId={card.node_id} name={card.name} />
      <div className="swipe-top">
        <SealMarks seals={hotel?.seals || []} tiers={[card.trust_tier]} />
        <Rating rating={card.rating} />
      </div>
      {verdict && <span className={`stamp ${verdict}`}>{verdict === "like" ? "Like" : "Pass"}</span>}
      <div className="swipe-name">{card.name}<small>{[card.size, card.agent && `agent ${card.agent}`].filter(Boolean).join(" · ")}</small></div>
      <div className="swipe-body">
        <ul className="features">
          {card.features.map(f => (
            <li key={f.key} className={f.ok ? "yes" : "no"}>
              <i><FeatureIcon name={f.key} /></i>{f.label}
            </li>
          ))}
        </ul>
        <div className="swipe-price">
          {card.over_budget_chf != null && <small>CHF {card.over_budget_chf} over</small>}
          CHF {card.price_chf}
        </div>
      </div>
    </article>
  );
}

/**
 * @param cards   the hotels to swipe (assistant/cards.py)
 * @param hotels  the wallet's hotel state, for the verified seals
 * @param onDone  (liked cards) => void, after the last card
 */
export default function Deck({ cards, hotels, onDone }) {
  const [index, setIndex] = useState(0);
  const [liked, setLiked] = useState([]);
  const [drag, setDrag] = useState(null);     // { dx, dy } while the finger moves the top card
  const [flying, setFlying] = useState(null); // "like" | "pass" while the top card leaves
  const start = useRef(null);

  function decide(verdict) {
    setFlying(verdict);
    setTimeout(() => {
      const nextLiked = verdict === "like" ? [...liked, cards[index]] : liked;
      setLiked(nextLiked);
      setFlying(null);
      setDrag(null);
      setIndex(index + 1);
      if (index + 1 >= cards.length && nextLiked.length) onDone(nextLiked);
    }, FLY_MS);
  }

  const handlers = {
    onPointerDown: e => {
      if (flying) return;
      try { e.currentTarget.setPointerCapture(e.pointerId); } catch { /* not every pointer can be captured */ }
      start.current = { x: e.clientX, y: e.clientY, t: performance.now() };
      setDrag({ dx: 0, dy: 0 });
    },
    onPointerMove: e => {
      if (!start.current) return;
      setDrag({ dx: e.clientX - start.current.x, dy: (e.clientY - start.current.y) * 0.2 });
    },
    onPointerUp: e => {
      if (!start.current) return;
      const dx = e.clientX - start.current.x, speed = Math.abs(dx) / Math.max(16, performance.now() - start.current.t);
      start.current = null;
      if (Math.abs(dx) > DECIDE_PX || (Math.abs(dx) > 30 && speed > FLICK_SPEED)) decide(dx > 0 ? "like" : "pass");
      else setDrag(null);
    },
    onPointerCancel: () => { start.current = null; setDrag(null); },
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
                     style={{ transform: "scale(.95) translateY(10px)", opacity: .6 }} handlers={{}} />
        )}
        <HotelCard key={cards[index].node_id} card={cards[index]} hotel={hotels[cards[index].node_id]}
                   style={top} handlers={handlers} verdict={verdict} />
      </div>
      <div className="deck-hint">{index + 1} of {cards.length} · swipe right to like, left to pass</div>
    </section>
  );
}
