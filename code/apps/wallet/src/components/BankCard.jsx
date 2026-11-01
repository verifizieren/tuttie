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

/** The bank's real logo, drawn white on the card (files in public/banks/). */
function BankLogo({ bank }) {
  return (
    <span className="bank-brand" aria-hidden="true">
      <img className={`bank-logo ${bank}`} src={`banks/${bank}-logo.svg`} alt="" />
    </span>
  );
}

/** @param index position in the stack (0 = top), @param color "blue" | "black" */
export default function BankCard({ index, color }) {
  return (
    <div className={`card bank bank-${color}`} style={{ "--i": index }}
         aria-label={color === "black" ? "UBS card" : "BKB card"}>
      <Chip />
      <BankLogo bank={color === "black" ? "ubs" : "bkb"} />
    </div>
  );
}
