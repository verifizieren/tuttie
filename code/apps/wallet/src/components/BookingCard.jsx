// The hotel's signed booking confirmation, kept small: the hotel, the price, the date and the
// booking id, a one-line note for a charge paid right after (the city tax), and what Tuttie
// checked about the hotel, folded into one line that opens on a tap. "No signature, no action"
// from the user's side: the hotel signs, Tuttie checks.
import { useState } from "react";
import { SealMarks } from "./Seals.jsx";

const ISSUERS = { "handelsregister-bs": "Registered in the Handelsregister", adobe: "Verified by Adobe" };

/** What Tuttie checked, as short lines the user understands. */
function checks(booking) {
  const lines = (booking.seals || []).filter(s => s.valid).map(s => ISSUERS[s.issuer] || `Sealed by ${s.issuer}`);
  if (booking.checked.includes("agreement")) lines.push("The hotel signed the agreed price");
  if (booking.checked.includes("commitments")) lines.push("The hotel signed the extras");
  lines.push("The hotel signed the booking");
  if (booking.checked.includes("approval")) lines.push("Approved by you");
  return lines;
}

const capitalize = text => text[0].toUpperCase() + text.slice(1);
const day = date => new Date(`${date}T12:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short" });

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
        <span className="booking-hotel">{booking.hotel}<small>{day(booking.date)} · {booking.id}</small>
          {booking.rate && <small>{booking.room} room · {booking.rate}</small>}</span>
        <span className="booking-total">CHF {booking.total}</span>
      </div>
      {booking.payments.map((payment, i) => (
        <div className="payment" key={i}><Check />{capitalize(payment.purpose)} CHF {payment.amount} paid</div>
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
