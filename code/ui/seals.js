// Seal badges shared by index.html and phone.html: issuer logo + name, coloured by tier.
// Logos are small inline SVGs so the pages need no external assets.

const SWISS_FLAG = `<svg viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="4" fill="#da291c"/>
  <path d="M13 6h6v7h7v6h-7v7h-6v-7H6v-6h7z" fill="#fff"/></svg>`;
const ADOBE_MARK = `<svg viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="4" fill="#fa0f00"/>
  <path d="M6 26 13.5 6H17L9.5 26zM18.5 6h3.5L26 26h-3.4zM15.6 15.2 20 26h-3.3l-1.3-3.6h-3.6z" fill="#fff"/></svg>`;
const SCALES = `<svg viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="4" fill="#3b4a6b"/>
  <text x="16" y="23" font-size="18" text-anchor="middle" fill="#fff">⚖</text></svg>`;

const ISSUERS = {
  "handelsregister-bs": { name: "Handelsregister BS", logo: SWISS_FLAG },
  "adobe": { name: "Adobe", logo: ADOBE_MARK },
  "bar-association-ch": { name: "Swiss Bar Association", logo: SCALES },
};

// Returns a <span class="seal ..."> for {issuer, tier, valid}; broken seals are struck through.
function sealBadge(seal) {
  const issuer = ISSUERS[seal.issuer] || { name: seal.tier === "grey" ? "self-signed" : seal.issuer, logo: "" };
  const badge = document.createElement("span");
  badge.className = "seal " + (seal.valid ? seal.tier : "invalid");
  badge.title = `${seal.valid ? seal.tier : "BROKEN"} seal from ${seal.issuer}`;
  badge.innerHTML = issuer.logo;  // trusted constant markup from this file only
  badge.append(seal.valid ? issuer.name : `${issuer.name} · broken`);
  return badge;
}
