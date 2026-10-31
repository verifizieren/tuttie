// The hotels to choose from, as cards to swipe through. Each card shows what the hotel offers
// and its pros and cons for this request, all built by Tuttie from signed facts
// (assistant/cards.py). The user marks favourites (Tuttie's recommendations start marked) and
// Tuttie then negotiates with those only.
import { useRef, useState } from "react";
import { SealMarks } from "./Seals.jsx";

/** A calm drawn scene per hotel, used until the hotel has a photo (public/hotels/<node_id>.jpg). */
function Illustration({ name }) {
  const hue = [...name].reduce((h, c) => (h * 31 + c.charCodeAt(0)) % 360, 7);
  return (
    <svg className="illustration" viewBox="0 0 320 140" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
      <defs>
        <linearGradient id={`sky-${hue}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={`hsl(${hue} 45% 32%)`} />
          <stop offset="1" stopColor={`hsl(${(hue + 30) % 360} 40% 16%)`} />
        </linearGradient>
      </defs>
      <rect width="320" height="140" fill={`url(#sky-${hue})`} />
      <circle cx="168" cy="30" r="14" fill="rgba(255,236,210,.5)" />
      <path d="M0 112 L40 70 h40 v-22 l22 -18 22 18 v22 h34 v-34 h48 v34 h30 l22 -26 22 26 h40 V140 H0z"
            fill="rgba(8,8,11,.55)" />
      <g fill="rgba(255,226,170,.75)">
        <rect x="88" y="62" width="6" height="8" rx="1" /><rect x="110" y="62" width="6" height="8" rx="1" />
        <rect x="168" y="58" width="6" height="8" rx="1" /><rect x="186" y="72" width="6" height="8" rx="1" />
        <rect x="200" y="58" width="6" height="8" rx="1" />
      </g>
      <path d="M0 122 q40 -8 80 0 t80 0 t80 0 t80 0 V140 H0z" fill="rgba(120,170,220,.25)" />
    </svg>
  );
}

function Photo({ nodeId, name }) {
  const [failed, setFailed] = useState(false);
  return (
    <div className="pick-photo">
      <Illustration name={name} />
      {!failed && <img src={`hotels/${nodeId}.jpg`} alt="" onError={() => setFailed(true)} />}
    </div>
  );
}

function Heart({ on }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 20.5s-8-4.9-8-11A4.5 4.5 0 0 1 12 6.6a4.5 4.5 0 0 1 8 2.9c0 6.1-8 11-8 11z"
            transform="translate(0 -1.5)" fill={on ? "currentColor" : "none"} stroke="currentColor"
            strokeWidth="1.8" strokeLinejoin="round" />
    </svg>
  );
}

function HotelCard({ card, hotel, favourite, onToggle, disabled }) {
  return (
    <article className={`pick${favourite ? " fav" : ""}`}>
      <Photo nodeId={card.node_id} name={card.name} />
      <button type="button" className="heart" aria-pressed={favourite} disabled={disabled}
              aria-label={favourite ? `Remove ${card.name} from favourites` : `Add ${card.name} to favourites`}
              onClick={onToggle}>
        <Heart on={favourite} />
      </button>
      {card.shortlisted && <span className="recommended">Recommended</span>}
      <div className="pick-body">
        <div className="pick-head">
          <SealMarks seals={hotel?.seals || []} tiers={[card.trust_tier]} />
          <span className="pick-name">{card.name}
            <small>{[card.size, card.agent && `agent ${card.agent}`].filter(Boolean).join(" · ")}</small>
          </span>
          <span className="pick-price">CHF {card.price_chf}</span>
        </div>
        {card.includes.length > 0 && <div className="pick-includes">Includes {card.includes.join(", ")}</div>}
        <ul className="pros">{card.pros.map(text => <li key={text}>{text}</li>)}</ul>
        {card.cons.length > 0 && <ul className="cons">{card.cons.map(text => <li key={text}>{text}</li>)}</ul>}
      </div>
    </article>
  );
}

/**
 * @param cards    the hotels to choose from (assistant/cards.py)
 * @param hotels   the wallet's hotel state, for the verified seals
 * @param picked   the favourites once sent (then the picker is read-only)
 * @param onPick   (favourite cards) => void
 */
export default function Picker({ cards, hotels, picked, onPick }) {
  const [favourites, setFavourites] = useState(() => new Set(cards.filter(c => c.shortlisted).map(c => c.node_id)));
  const [index, setIndex] = useState(0);
  const track = useRef(null);
  const done = Boolean(picked);
  const chosen = done ? new Set(picked) : favourites;

  function toggle(nodeId) {
    setFavourites(current => {
      const next = new Set(current);
      next.has(nodeId) ? next.delete(nodeId) : next.add(nodeId);
      return next;
    });
  }

  function onScroll() {
    const el = track.current;
    if (el) setIndex(Math.round(el.scrollLeft / Math.max(1, el.firstChild?.offsetWidth || 1)));
  }

  const count = chosen.size;
  return (
    <section className="picker">
      <div className="picker-title">{done ? "Your favourites" : "Pick your favourites"}</div>
      <div className="picker-track" data-hscroll ref={track} onScroll={onScroll}>
        {cards.map(card => (
          <HotelCard key={card.node_id} card={card} hotel={hotels[card.node_id]} favourite={chosen.has(card.node_id)}
                     disabled={done} onToggle={() => toggle(card.node_id)} />
        ))}
      </div>
      <div className="picker-dots" aria-hidden="true">
        {cards.map((card, i) => <i key={card.node_id} className={i === index ? "on" : ""} />)}
      </div>
      {!done && (
        <button type="button" className="picker-go" disabled={!count}
                onClick={() => onPick(cards.filter(c => favourites.has(c.node_id)))}>
          {count ? `Negotiate with ${count === 1 ? "this hotel" : `${count} hotels`}` : "Pick at least one hotel"}
        </button>
      )}
    </section>
  );
}
