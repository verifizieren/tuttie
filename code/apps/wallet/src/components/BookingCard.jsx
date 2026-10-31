// The hotel's signed booking confirmation, kept small: the hotel, the price, the date and the
// booking id, a one-line note for a charge paid right after (the city tax), and what Tuttie
// checked about the hotel, folded into one line that opens on a tap. "No signature, no action"
// from the user's side: the hotel signs, Tuttie checks.
import { useState } from "react";
import { SealMarks } from "./Seals.jsx";

const ISSUERS = { "handelsregister-bs": "Registered in the Handelsregister", adobe: "Verified by Adobe" };

/** What Tuttie checked, as short lines the user understands. */
function checks(booking) {
  const checked = booking.checked || [];  // an older booking kept in the history may have none
  const lines = (booking.seals || []).filter(s => s.valid).map(s => ISSUERS[s.issuer] || `Sealed by ${s.issuer}`);
  if (checked.includes("agreement")) lines.push("The hotel signed the agreed price");
  if (checked.includes("commitments")) lines.push("The hotel signed the extras");
  lines.push("The hotel signed the booking");
  if (checked.includes("approval")) lines.push("Approved by you");
  return [...new Set(lines)];  // two seals from one issuer read as one line (and one React key)
}

const capitalize = (text = "") => text.charAt(0).toUpperCase() + text.slice(1);

/** "14 Nov" for an ISO date; the date as given if it cannot be read. */
function day(date) {
  const parsed = new Date(`${date}T12:00:00`);
  return Number.isNaN(parsed.getTime()) ? date || "" : parsed.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

function Check() {
  return (
    <svg className="check-ok" viewBox="0 0 20 20" aria-hidden="true">
      <circle cx="10" cy="10" r="10" />
      <path d="M5.8 10.4l2.7 2.7 5.7-6" />
    </svg>
  );
}

export default function BookingCard({ booking }) {
  const [open, setOpen] = useState(false);
  const lines = checks(booking);
  return (
    <div className="booking">
      <div className="booking-top">
        <SealMarks seals={booking.seals} />
        <span className="booking-hotel">{booking.hotel}<small>{[day(booking.date), booking.id].filter(Boolean).join(" · ")}</small>
          {booking.rate && <small>{booking.room} room · {booking.rate}</small>}</span>
        <span className="booking-total">CHF {booking.total}</span>
      </div>
      {(booking.payments || []).map((payment, i) => (
        <div className="payment" key={i}><Check />{capitalize(payment.purpose || "charge")} CHF {payment.amount} paid</div>
      ))}
      <button type="button" className="checks-toggle" aria-expanded={open} onClick={() => setOpen(!open)}>
        <Check /> Checked by Tuttie <span className="checks-count">{lines.length}</span>
        <span className="chevron" aria-hidden="true">{open ? "⌃" : "⌄"}</span>
      </button>
      {open && (
        <ul className="checks-list">
          {lines.map(line => <li key={line}>{line}</li>)}
        </ul>
      )}
    </div>
  );
}
