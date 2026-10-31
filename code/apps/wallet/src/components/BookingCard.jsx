// The hotel's signed booking confirmation, and the signatures its action gate checked before
// it booked (aps/gate.py): "No signature, no action" made visible. Each check is listed the way
// the user knows it; the hotel names them in `checked`.
import { SealMarks } from "./Seals.jsx";

const CHECKS = {
  caller: "Tuttie is a sealed agent",
  signature: "Signed by Tuttie",
  delegation: "You let Tuttie book",
  agreement: "The hotel's signed deal",
  approval: "Approved by you",
  mandate: "Your payment mandate",
  commitments: "The hotel's signed extras",
};

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
      {booking.checked.length > 0 && (
        <div className="seal-list checks">
          <div className="seal-head">Checked by the hotel before booking</div>
          {booking.checked.map(check => (
            <div className="seal-row" key={check}>
              <Check />
              <span className="seal-text"><b>{CHECKS[check] || check}</b></span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
