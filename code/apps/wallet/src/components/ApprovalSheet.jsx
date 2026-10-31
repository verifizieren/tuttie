// The approval sheet: Tuttie wants to pay a business and waits for the user. Approving runs a
// Face ID-style confirmation (a short scan, then a check) before the decision is sent; the
// assistant signs it with the user's key, and the hotel only books with that signature and
// only for exactly this amount. Declining is immediate.
import { useState } from "react";
import { decide } from "../lib/api.js";

const SCAN_MS = 1100;   // how long the face scan runs
const CHECK_MS = 550;   // how long the check is shown before the sheet goes

const wait = ms => new Promise(resolve => setTimeout(resolve, ms));

function FaceScan({ done }) {
  return (
    <div className="faceid" aria-live="polite">
      {done ? (
        <svg className="faceid-ok" viewBox="0 0 52 52" aria-label="Approved">
          <circle cx="26" cy="26" r="25" />
          <path d="M15 27l7 7 15-16" />
        </svg>
      ) : (
        <div className="faceid-scan" aria-label="Confirming with Face ID"><i /><i /><i /><i /></div>
      )}
      <span>{done ? "Approved" : "Face ID"}</span>
    </div>
  );
}

export default function ApprovalSheet({ approval }) {
  const [stage, setStage] = useState("ask");  // ask | scan | done | sending
  if (!approval) return null;

  async function approve() {
    setStage("scan");
    await wait(SCAN_MS);
    setStage("done");
    await wait(CHECK_MS);
    await send("approved");
  }

  async function send(decision) {
    setStage("sending");
    try {
      await decide(approval.id, decision);
    } catch {
      setStage("ask");  // let the user try again
    }
  }

  const tiers = approval.seals.filter(s => s.valid).map(s => s.tier);
  return (
    <div className="sheet" role="dialog" aria-label="Approve payment">
      <div className="sheet-hotel">
        <span className="dots">{tiers.map((t, i) => <i key={i} className={`dot ${t}`} />)}</span>
        {approval.hotel}
      </div>
      <div className="sheet-amount">CHF {approval.amount}</div>
      <div className="sheet-summary">{approval.summary.replace(/^Waiting for your phone\.\s*/, "")}</div>
      {stage === "ask" ? (
        <div className="sheet-buttons">
          <button type="button" className="decline" onClick={() => send("declined")}>Decline</button>
          <button type="button" className="approve" onClick={approve}>Approve</button>
        </div>
      ) : (
        <FaceScan done={stage !== "scan"} />
      )}
    </div>
  );
}
