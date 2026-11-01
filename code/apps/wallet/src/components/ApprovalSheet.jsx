// The approval sheet: Tuttie wants to pay a business and waits for the user. A booking shows the
// terms the user's key signs with the amount (room, night and rate, i.e. the cancellation
// terms), so a flexible and a non-refundable rate never look the same. Approving runs a
// Face ID-style confirmation (a short scan) before the decision is sent; the assistant signs it
// with the user's key, and the hotel only books with that signature and only for exactly this
// amount. Declining is sent right away. While a decision travels the sheet names it
// ("Declining…"), and the final mark shows what the server recorded. A failed send shows why
// and leaves the buttons ready for another try, also when no answer came at all (after 15 s,
// lib/api.js); the event stream is the other way the server's decision arrives: once it says
// the approval was decided, the sheet finishes even if the answer to its own call never comes.
// An approval that no longer waits (already
// decided or expired) says so and the sheet goes. A booking may also offer a mandate for a
// small charge that follows (the city tax): with the switch on, the user's key signs it too
// and Tuttie pays that charge without asking again.
import { useEffect, useRef, useState } from "react";
import { decide } from "../lib/api.js";
import { doneLabel, failureOf, recordedDecision, sendingLabel } from "../lib/approval.js";
import { SealList, SealMarks } from "./Seals.jsx";

const SCAN_MS = 1100;   // how long the face scan runs before an approval is sent
const GONE_MS = 2600;   // how long "already decided or expired" is shown before the sheet goes
const DONE_MS = 1400;   // how long the final mark (checkmark or X) is shown before the sheet slides away
const LEAVE_MS = 350;   // the slide down (wallet.css .sheet.leaving)

const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
// The night as "14 Nov"; a date in another form is shown as it came.
function day(date) {
  const parsed = new Date(`${date}T12:00:00`);
  return Number.isNaN(parsed.getTime()) ? date : parsed.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

/** The Face ID glyph as on an iPhone: rounded corner brackets around a simple face (eyes, an
 *  L-shaped nose, a smile). Scanning, the face turns a little and the brackets pulse; once
 *  approved, the face gives way to a checkmark drawn inside the same brackets. */
function FaceId({ done = false }) {
  return (
    <svg className={done ? "faceid-glyph faceid-done" : "faceid-glyph"} viewBox="0 0 60 60" aria-hidden="true">
      <g className="faceid-frame">
        <path d="M4 18V10a6 6 0 0 1 6-6h8M42 4h8a6 6 0 0 1 6 6v8M56 42v8a6 6 0 0 1-6 6h-8M18 56h-8a6 6 0 0 1-6-6v-8" />
      </g>
      <g className="faceid-face">
        <path d="M21 22v5M39 22v5M30 22v11h-2.5M22 40q8 6 16 0" />
      </g>
      {done && <path className="faceid-check" d="M19 31l7.5 7.5L41.5 23" />}
    </svg>
  );
}

function Progress({ stage, decision }) {
  const approved = decision === "approved";
  if (stage === "done") {
    return (
      <div className="faceid" aria-live="polite">
        {approved ? <FaceId done />
                  : <svg className="faceid-ok faceid-no" viewBox="0 0 52 52" aria-hidden="true">
                      <circle cx="26" cy="26" r="25" /><path d="M18 18l16 16M34 18L18 34" />
                    </svg>}
        <span>{doneLabel(decision)}</span>
      </div>
    );
  }
  return (
    <div className="faceid" aria-live="polite">
      {approved ? <FaceId /> : <div className="faceid-wait" aria-hidden="true" />}
      <span>{stage === "scan" ? "Face ID" : sendingLabel(decision)}</span>
    </div>
  );
}

/** What replaces the sheet if it cannot be shown (an approval in a shape this version does not
 *  expect): the user can still decline, so nothing waits on a sheet nobody can see. */
export function ApprovalFallback({ approval, onGone }) {
  const [state, setState] = useState("ask");  // ask | sending | failed | done
  if (!approval) return null;
  async function decline() {
    setState("sending");
    try {
      await decide(approval.id, "declined", false);
      setState("done");
    } catch (e) {
      if (failureOf(e).gone) return setState("done");
      setState("failed");
    }
  }
  return (
    <div className="sheet" role="dialog" aria-label="Approve payment">
      <p className="sheet-error" role="alert">
        {state === "done" ? "Declined." : "This payment request cannot be shown, so it cannot be approved here."}
        {state === "failed" && " Declining did not work, please try again."}
      </p>
      <div className="sheet-buttons sheet-close">
        {state === "done" ? <button type="button" className="decline" onClick={onGone}>Close</button>
          : <button type="button" className="decline" disabled={state === "sending"} onClick={decline}>Decline</button>}
      </div>
    </div>
  );
}

// `note`: a passing line from the wallet while the sheet covers the card (e.g. "Decide on the
// booking first" after the user tapped New chat); the line under Tuttie's eyes is hidden then.
// `onDecide(approval)` when the user decides: the wallet keeps the sheet while it finishes, even
// once the server stopped waiting; `recorded`: the decision the server streamed for this approval
// (lib/approval.js serverDecision), which finishes a sheet still sending; `onFinished(id, decided)` after the final mark was shown and the
// sheet left (decided), or after a failed send while the approval still waits (not decided).
export default function ApprovalSheet({ approval, onGone, note = "", recorded = null, onDecide, onFinished }) {
  const [stage, setStage] = useState("ask");     // ask | scan | sending | done | gone
  const [leaving, setLeaving] = useState(false); // sliding away after the final mark
  const [decision, setDecision] = useState(null); // the chosen decision, then the recorded one
  const [error, setError] = useState("");
  const [allow, setAllow] = useState(true);      // sign the offered mandate as well
  const busy = useRef(false);                    // one decision in flight at a time (double taps)
  const finished = useRef(false);                // the final mark is shown once: by the answer or the stream
  const gone = useRef(false);                    // the server said this approval no longer waits
  const unmounted = useRef(false);
  const latest = useRef({ id: approval?.id, onFinished });
  latest.current = { id: approval?.id, onFinished };

  // A sheet that goes while its decision is still open (another sheet took its place) tells the
  // wallet, so the decision is never left "finishing" with no sheet to end it.
  useEffect(() => () => {
    unmounted.current = true;
    if (busy.current && !finished.current) latest.current.onFinished?.(latest.current.id, gone.current);
  }, []);

  // The server's decision arrived on the event stream while the sheet still waits for the answer
  // to its call (which may never come): finish with what the server recorded.
  useEffect(() => {
    if (recorded && stage === "sending") finish(recorded);
  }, [recorded, stage]);  // eslint-disable-line react-hooks/exhaustive-deps

  // An approval that no longer waits: say so briefly, then let the sheet go.
  useEffect(() => {
    if (stage !== "gone" || !onGone) return undefined;
    const timer = setTimeout(onGone, GONE_MS);
    return () => clearTimeout(timer);
  }, [stage, onGone]);

  if (!approval) return null;
  const offer = approval.offerMandate;

  // The final mark for the recorded decision, then the sheet slides away; only the first of the
  // call's answer and the stream's event does this, a later one changes nothing.
  async function finish(recordedAs) {
    if (finished.current) return;
    finished.current = true;
    setError("");
    setDecision(recordedAs);
    setStage("done");
    await wait(DONE_MS);  // the checkmark (or X) is seen in full
    setLeaving(true);
    await wait(LEAVE_MS);
    onFinished?.(approval.id, true);
  }

  async function choose(chosen) {
    if (busy.current) return;
    busy.current = true;
    setError("");
    setDecision(chosen);
    onDecide?.(approval);
    if (chosen === "approved") {
      setStage("scan");
      await wait(SCAN_MS);
    }
    setStage("sending");
    try {
      const result = await decide(approval.id, chosen, chosen === "approved" && Boolean(offer) && allow);
      await finish(recordedDecision(result, chosen));
    } catch (e) {
      if (finished.current) return;  // the stream already showed the decision: a late failure changes nothing
      const failure = failureOf(e);
      gone.current = failure.gone;
      if (unmounted.current) return onFinished?.(approval.id, failure.gone);  // no sheet left to say it
      setError(failure.message);
      setStage(failure.gone ? "gone" : "ask");
      busy.current = failure.gone;  // retry only while the approval still waits
      if (!failure.gone) onFinished?.(approval.id, false);  // still waiting: shown as the server's approval again
    }
  }

  return (
    <div className={leaving ? "sheet leaving" : "sheet"} role="dialog" aria-label="Approve payment" data-scroll>
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
      {!error && note && <p className="sheet-note" role="status">{note}</p>}
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
