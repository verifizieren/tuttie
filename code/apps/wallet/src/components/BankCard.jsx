// Swiss bank cards in the wallet stack. They stay intentionally free of personal details.

/** Contact lines of an EMV chip, drawn over the metal chip. */
function Chip() {
  return (
    <span className="chip">
      <svg viewBox="0 0 40 30" aria-hidden="true">
        <path d="M0 10h13M0 20h13M27 10h13M27 20h13M13 0v30M27 0v30M13 15h14" />
      </svg>
    </span>
  );
}

function UbsBrand() {
  return (
    <span className="bank-brand ubs-brand" aria-hidden="true">
      <svg className="ubs-keys" viewBox="0 0 42 30">
        <g fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="7" cy="15" r="4.5" />
          <path d="M11.5 15h24l4-4M31 15l4 4M26 15v4" />
          <circle cx="13" cy="6" r="3.5" />
          <path d="M16 8l18 13 5-1M31 19l-1 4" />
          <circle cx="13" cy="24" r="3.5" />
          <path d="M16 22L34 9l5 1M31 11l-1-4" />
        </g>
      </svg>
      <b>UBS</b>
    </span>
  );
}

function ZkbBrand() {
  return (
    <span className="bank-brand zkb-brand" aria-hidden="true">
      <span className="swiss-mark"><i /><i /></span>
      <span><b>ZKB</b><small>Zürcher Kantonalbank</small></span>
    </span>
  );
}

/** @param index position in the stack (0 = top), @param color "blue" | "black" */
export default function BankCard({ index, color }) {
  return (
    <div className={`card bank bank-${color}`} style={{ "--i": index }}
         aria-label={color === "black" ? "UBS card" : "ZKB card"}>
      <Chip />
      {color === "black" ? <UbsBrand /> : <ZkbBrand />}
    </div>
  );
}
