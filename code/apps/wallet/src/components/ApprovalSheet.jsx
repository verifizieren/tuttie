// The approval sheet: Tuttie wants to pay a business and waits for the user. A booking shows the
// terms the user's key signs with the amount (room, night and rate, i.e. the cancellation
// terms), so a flexible and a non-refundable rate never look the same. Approving runs a
// Face ID-style confirmation (a short scan) before the decision is sent; the assistant signs it
// with the user's key, and the hotel only books with that signature and only for exactly this
// amount. Declining is sent right away. While a decision travels the sheet names it
// ("Declining…"), and the final mark shows what the server recorded. A failed send shows why
// and leaves the buttons ready for another try; an approval that no longer waits (already
// decided or expired) says so and the sheet goes. A booking may also offer a mandate for a
// small charge that follows (the city tax): with the switch on, the user's key signs it too
// and Tuttie pays that charge without asking again.
import { useEffect, useRef, useState } from "react";
import { decide } from "../lib/api.js";
import { doneLabel, failureOf, recordedDecision, sendingLabel } from "../lib/approval.js";
import { SealList, SealMarks } from "./Seals.jsx";

const SCAN_MS = 1100;   // how long the face scan runs before an approval is sent
const GONE_MS = 2600;   // how long "already decided or expired" is shown before the sheet goes

const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
const day = date => new Date(`${date}T12:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short" });

function Progress({ stage, decision }) {
  if (stage === "done") {
    const approved = decision === "approved";
    return (
      <div className="faceid" aria-live="polite">
        <svg className={approved ? "faceid-ok" : "faceid-ok faceid-no"} viewBox="0 0 52 52" aria-label={doneLabel(decision)}>
          <circle cx="26" cy="26" r="25" />
          <path d={approved ? "M15 27l7 7 15-16" : "M18 18l16 16M34 18L18 34"} />
        </svg>
        <span>{doneLabel(decision)}</span>
      </div>
    );
  }
  const scanning = decision === "approved";
  return (
    <div className="faceid" aria-live="polite">
      {scanning ? <div className="faceid-scan" aria-label="Confirming with Face ID"><i /><i /><i /><i /></div>
                : <div className="faceid-wait" aria-hidden="true" />}
      <span>{stage === "scan" ? "Face ID" : sendingLabel(decision)}</span>
    </div>
  );
}

export default function ApprovalSheet({ approval, onGone }) {
  const [stage, setStage] = useState("ask");     // ask | scan | sending | done | gone
  const [decision, setDecision] = useState(null); // the chosen decision, then the recorded one
  const [error, setError] = useState("");
  const [allow, setAllow] = useState(true);      // sign the offered mandate as well
  const busy = useRef(false);                    // one decision in flight at a time (double taps)

  // An approval that no longer waits: say so briefly, then let the sheet go.
  useEffect(() => {
    if (stage !== "gone" || !onGone) return undefined;
    const timer = setTimeout(onGone, GONE_MS);
    return () => clearTimeout(timer);
  }, [stage, onGone]);

  if (!approval) return null;
  const offer = approval.offerMandate;

  async function choose(chosen) {
    if (busy.current) return;
    busy.current = true;
    setError("");
    setDecision(chosen);
    if (chosen === "approved") {
      setStage("scan");
      await wait(SCAN_MS);
    }
    setStage("sending");
    try {
      const result = await decide(approval.id, chosen, chosen === "approved" && Boolean(offer) && allow);
      setDecision(recordedDecision(result, chosen));
      setStage("done");
    } catch (e) {
      const failure = failureOf(e);
      setError(failure.message);
      setStage(failure.gone ? "gone" : "ask");
      busy.current = failure.gone;  // retry only while the approval still waits
    }
  }

  return (
    <div className="sheet" role="dialog" aria-label="Approve payment" data-scroll>
      <div className="sheet-hotel">
        <SealMarks seals={approval.seals} />
        {approval.hotel}
      </div>
      <div className="sheet-amount">CHF {approval.amount}</div>
      {approval.terms && (
        <div className="sheet-terms">
          {approval.terms.room_type} room · {day(approval.terms.date)}
          {approval.terms.rate && <span>{approval.terms.rate}</span>}
        </div>
      )}
      <SealList seals={approval.seals} uid={approval.uid} />
      {offer && (
        <label className="mandate">
          <span>Also pay {offer.purpose} (CHF {offer.price_chf})</span>
          <input type="checkbox" role="switch" checked={allow} disabled={stage !== "ask"}
                 onChange={e => setAllow(e.target.checked)} />
        </label>
      )}
      {error && <p className="sheet-error" role="alert">{error}</p>}
      {stage === "ask" && (
        <div className="sheet-buttons">
          <button type="button" className="decline" onClick={() => choose("declined")}>Decline</button>
          <button type="button" className="approve" onClick={() => choose("approved")}>Approve</button>
        </div>
      )}
      {stage === "gone" && onGone && (
        <div className="sheet-buttons sheet-close">
          <button type="button" className="decline" onClick={onGone}>Close</button>
        </div>
      )}
      {["scan", "sending", "done"].includes(stage) && <Progress stage={stage} decision={decision} />}
    </div>
  );
}
