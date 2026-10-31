// A generic bank card in the stack. It only resembles a card: colour and chip, no name,
// number or other details.

/** Contact lines of an EMV chip, drawn over the gold chip. */
function Chip() {
  return (
    <span className="chip">
      <svg viewBox="0 0 40 30" aria-hidden="true">
        <path d="M0 10h13M0 20h13M27 10h13M27 20h13M13 0v30M27 0v30M13 15h14" />
      </svg>
    </span>
  );
}

/** @param index position in the stack (0 = top), @param color "blue" | "black" */
export default function BankCard({ index, color }) {
  return (
    <div className={`card bank bank-${color}`} style={{ "--i": index }}>
      <Chip />
    </div>
  );
}
