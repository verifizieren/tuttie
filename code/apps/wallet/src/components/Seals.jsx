// APS seals the way the wallet shows them: who vouches for a business, with the issuer's mark.
// Gold = the Swiss commercial register (flag, name and the business's UID), blue = Adobe (logo
// and name). Only seals the assistant verified are shown as seals; a forged one is shown as
// forged. The UID is signed into every seal, so it is shown only inside a valid gold seal. A
// shield marks every verified signature, so the seals read as marks of authenticity.

/** The Swiss flag as a rounded tile. */
function SwissFlag() {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="7" fill="#ff1f1f" />
      <path d="M13 6h6v7h7v6h-7v7h-6v-7H6v-6h7z" fill="#fff" />
    </svg>
  );
}

/** Adobe's mark (the red "A") as a rounded tile. */
function AdobeMark() {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="7" fill="#fa0f00" />
      <path d="M6.5 7h6.6L6.5 25z M18.9 7h6.6v18z M16 13.3l4.6 11.7h-3.1l-1.4-3.6h-3.4z" fill="#fff" />
    </svg>
  );
}

/** A neutral tile for issuers without a known mark. */
function GenericMark() {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="7" fill="#3a3a3f" />
      <path d="M16 7l7 3v5c0 4.5-3 8.4-7 10-4-1.6-7-5.5-7-10v-5z" fill="none" stroke="#fff" strokeWidth="2" />
    </svg>
  );
}

// A shield: the sign that an authority signed for this business.
const SHIELD = "M12 2.2l7.6 2.9v6.1c0 4.7-3.2 8.9-7.6 10.6-4.4-1.7-7.6-5.9-7.6-10.6V5.1z";

/** The shield with a check, tinted by tier: this authority's signature verified. */
function SealBadge({ tier }) {
  return (
    <svg className={`seal-badge ${tier}`} viewBox="0 0 24 24" aria-hidden="true">
      <path d={SHIELD} />
      <path d="M8.2 12.2l2.6 2.6 5-5.4" fill="none" stroke="#fff" strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** A small shield for the corner of an issuer's tile. */
function MiniShield({ tier }) {
  return (
    <svg className={`mini-shield ${tier}`} viewBox="0 0 24 24" aria-hidden="true">
      <path d={SHIELD} />
      <path d="M8.4 12.2l2.5 2.5 4.8-5.2" fill="none" stroke="#fff" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** The plain shield outline, for headings. */
export function ShieldIcon() {
  return (
    <svg className="shield-icon" viewBox="0 0 24 24" aria-hidden="true">
      <path d={SHIELD} fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
      <path d="M8.6 12.2l2.4 2.4 4.6-5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

const ISSUERS = {
  "handelsregister-bs": { mark: SwissFlag, name: "Handelsregister", about: "Basel-Stadt" },
  adobe: { mark: AdobeMark, name: "Adobe", about: "Verified business" },
  "bar-association-ch": { mark: GenericMark, name: "Swiss Bar Association", about: "Licensed lawyer" },
};

const issuer = id => ISSUERS[id] || { mark: GenericMark, name: id, about: "Seal" };

/** Small issuer marks for a list row (the flag and/or the Adobe logo), each with a shield. */
export function SealMarks({ seals = [], tiers = [] }) {
  // Before an offer arrives only the tier is known; show the tier's issuer.
  const shown = seals.length ? seals.filter(s => s.valid).map(s => ({ id: s.issuer, tier: s.tier }))
    : tiers.filter(t => t === "gold" || t === "blue")
           .map(t => ({ id: t === "gold" ? "handelsregister-bs" : "adobe", tier: t }));
  return (
    <span className="marks" aria-label={`signed by ${shown.map(s => issuer(s.id).name).join(", ")}`}>
      {shown.map((s, i) => {
        const Mark = issuer(s.id).mark;
        return <i key={i}><Mark /><MiniShield tier={s.tier} /></i>;
      })}
    </span>
  );
}

/** The seals as an inset grouped list: issuer mark, name, what it vouches for, badge. */
export function SealList({ seals = [], uid = null }) {
  if (!seals.length) return null;
  return (
    <div className="seal-list">
      <div className="seal-head"><ShieldIcon /> Signed and verified by</div>
      {seals.map((seal, i) => {
        const { mark: Mark, name, about } = issuer(seal.issuer);
        if (!seal.valid) {
          return (
            <div className="seal-row forged" key={i}>
              <i className="seal-mark"><Mark /></i>
              <span className="seal-text"><b>Forged seal</b><small>Claims {name}; the signature does not match</small></span>
              <span className="seal-x" aria-hidden="true">!</span>
            </div>
          );
        }
        return (
          <div className="seal-row" key={i}>
            <i className="seal-mark"><Mark /></i>
            <span className="seal-text">
              <b>{name}</b><small>{about}</small>
              {seal.tier === "gold" && uid && <small className="uid">UID {uid}</small>}
            </span>
            <SealBadge tier={seal.tier} />
          </div>
        );
      })}
    </div>
  );
}
