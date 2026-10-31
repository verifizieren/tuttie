// APS seals the way the wallet shows them: who vouches for a business, with the issuer's mark.
// Gold = the Swiss commercial register (flag, name and the business's UID), blue = Adobe (logo
// and name). Only seals the assistant verified are shown as seals; a forged one is shown as
// forged. The UID is signed into every seal, so it is shown only inside a valid gold seal.

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

/** The scalloped "checkmark seal" badge, tinted by tier. */
function SealBadge({ tier }) {
  return (
    <svg className={`seal-badge ${tier}`} viewBox="0 0 24 24" aria-hidden="true">
      <path d={SCALLOP} />
      <path d="M7.6 12.3l3 3 5.8-6.2" fill="none" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

// A circle with 12 soft bumps (like Apple's checkmark.seal), built once.
const SCALLOP = (() => {
  const n = 12, points = [];
  for (let i = 0; i < 2 * n; i++) {
    const r = i % 2 ? 9.2 : 11.4, a = (i * Math.PI) / n;
    points.push([12 + r * Math.cos(a), 12 + r * Math.sin(a)]);
  }
  const mid = (p, q) => [(p[0] + q[0]) / 2, (p[1] + q[1]) / 2];
  const f = p => p.map(v => v.toFixed(2)).join(" ");
  const at = i => points[i % points.length];
  // Every point is a curve control, so the edge waves between the outer and inner radius.
  let d = `M${f(mid(at(0), at(1)))}`;
  for (let i = 1; i <= points.length; i++) d += ` Q${f(at(i))} ${f(mid(at(i), at(i + 1)))}`;
  return d + "Z";
})();

const ISSUERS = {
  "handelsregister-bs": { mark: SwissFlag, name: "Handelsregister", about: "Basel-Stadt" },
  adobe: { mark: AdobeMark, name: "Adobe", about: "Verified business" },
  "bar-association-ch": { mark: GenericMark, name: "Swiss Bar Association", about: "Licensed lawyer" },
};

const issuer = id => ISSUERS[id] || { mark: GenericMark, name: id, about: "Seal" };

/** Small issuer marks for a list row: the flag and/or the Adobe logo. */
export function SealMarks({ seals = [], tiers = [] }) {
  // Before an offer arrives only the tier is known; show the tier's issuer.
  const shown = seals.length ? seals.filter(s => s.valid).map(s => s.issuer)
    : tiers.map(t => (t === "gold" ? "handelsregister-bs" : t === "blue" ? "adobe" : null)).filter(Boolean);
  return (
    <span className="marks" aria-label={`verified by ${shown.map(id => issuer(id).name).join(", ")}`}>
      {shown.map((id, i) => { const Mark = issuer(id).mark; return <i key={i}><Mark /></i>; })}
    </span>
  );
}

/** The seals as an inset grouped list: issuer mark, name, what it vouches for, badge. */
export function SealList({ seals = [], uid = null }) {
  if (!seals.length) return null;
  return (
    <div className="seal-list">
      <div className="seal-head">Verified by</div>
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
