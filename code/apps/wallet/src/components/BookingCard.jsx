// The hotel's signed booking confirmation, and what Tuttie checked about the hotel before and
// after it booked: who vouches for the hotel (its verified seals), the hotel's own signed deal
// or extras, its signed confirmation, and the user's approval. "No signature, no action" made
// visible from the user's side: the hotel signs, Tuttie checks.
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

/** "double room 2026-11-14" or "double" → "double room" (the date is shown on its own). */
const roomName = (room, date) => `${room.replace(date, "").replace(/\s*room\s*$/, "").trim()} room`;

function Check() {
  return (
    <svg className="check-ok" viewBox="0 0 20 20" aria-hidden="true">
      <circle cx="10" cy="10" r="10" />
      <path d="M5.8 10.4l2.7 2.7 5.7-6" />
    </svg>
  );
}

export default function BookingCard({ booking }) {
  return (
    <div className="booking">
      <div className="booking-top">
        <SealMarks seals={booking.seals} />
        <span className="booking-hotel">{booking.hotel}<small>{booking.date} · {roomName(booking.room, booking.date)}</small></span>
        <span className="booking-total">CHF {booking.total}</span>
      </div>
      <div className="booking-id">Booking <b>{booking.id}</b></div>
      {booking.payments.map((payment, i) => (
        <div className="payment" key={i}>
          <Check />
          <span><b>{payment.purpose[0].toUpperCase() + payment.purpose.slice(1)} CHF {payment.amount}</b>
            <small>{payment.paidWith === "mandate" ? "Paid with your mandate" : "Paid after your approval"}</small>
          </span>
        </div>
      ))}
      <div className="seal-list checks">
        <div className="seal-head">Checked by Tuttie</div>
        {checks(booking).map(line => (
          <div className="seal-row" key={line}>
            <Check />
            <span className="seal-text"><b>{line}</b></span>
          </div>
        ))}
      </div>
    </div>
  );
}
