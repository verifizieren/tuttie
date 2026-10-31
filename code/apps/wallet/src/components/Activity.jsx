// The human view of the marketplace, under Tuttie's eyes: what Tuttie asked for, which hotels
// answered with which offer, the shortlist, the negotiation and Tuttie's answer. Tapping a
// hotel shows who vouches for it (its seals) and what its offer includes.
import { useEffect, useRef, useState } from "react";
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

/** Tuttie's answer without the timeline citations ([3]) and with **bold** kept as bold. */
function Answer({ text }) {
  const clean = text.replace(/\s*\[\d+\]/g, "");
  return (
    <div className="answer">
      {clean.split(/(\*\*[^*]+\*\*)/).map((part, i) =>
        part.startsWith("**") ? <b key={i}>{part.slice(2, -2)}</b> : <span key={i}>{part}</span>)}
    </div>
  );
}

/** Shortlisted hotels first, then the other offers by price, then hotels still thinking. */
function order(hotels) {
  const rank = h => (h.shortlisted ? 0 : h.offer ? 1 : 2);
  return Object.entries(hotels).sort(([, a], [, b]) =>
    rank(a) - rank(b) || (a.agreed ?? a.offer?.price_chf ?? 1e9) - (b.agreed ?? b.offer?.price_chf ?? 1e9));
}

export default function Activity({ state }) {
  const box = useRef(null);
  const [openId, setOpenId] = useState(null);
  // Tuttie's answer comes last; bring it into view when it arrives.
  useEffect(() => {
    if (state.answer) box.current?.scrollTo({ top: box.current.scrollHeight, behavior: "smooth" });
  }, [state.answer]);

  if (!state.request && !state.answer) return null;
  return (
    <div className="activity" ref={box}>
      {state.request && <RequestCard request={state.request} />}
      {order(state.hotels).map(([nodeId, hotel]) => (
        <HotelRow key={nodeId} hotel={hotel} overBudget={state.shortlistDone && hotel.offer && !hotel.shortlisted}
                  open={openId === nodeId} onToggle={() => setOpenId(openId === nodeId ? null : nodeId)} />
      ))}
      {state.skipped.map((business, i) => <SkippedRow key={i} business={business} />)}
      {state.answer && <Answer text={state.answer} />}
    </div>
  );
}
