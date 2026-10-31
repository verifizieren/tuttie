// Small line icons for the hotel features on the cards (assistant/cards.py keys). Drawn in
// currentColor, so the card paints them green (yes) or red (no).

const PATHS = {
  // a dog's head with floppy ears
  dog: "M8 6.5 5 5.2 4 10.5l2.4.9M16 6.5l3-1.3 1 5.3-2.4.9M8 6.5h8l1.6 5v3.3a5.6 5.6 0 0 1-11.2 0v-3.3zM10 11.5h.01M14 11.5h.01M11 15.2h2l-1 1.2z",
  // a cot
  kids: "M4 18V6M20 18V6M4 15h16M4 9h16M8 9v6M12 9v6M16 9v6",
  // a crescent moon
  quiet: "M19.5 14.5A8 8 0 0 1 9.5 4.5a8 8 0 1 0 10 10z",
  // a clock
  late: "M12 3.5a8.5 8.5 0 1 0 0 17 8.5 8.5 0 0 0 0-17zM12 7.5V12l3 2",
  // a train front
  station: "M7 4h10a2 2 0 0 1 2 2v9a3 3 0 0 1-3 3H8a3 3 0 0 1-3-3V6a2 2 0 0 1 2-2zM5 11h14M9 15h.01M15 15h.01M8 18l-2 2.5M16 18l2 2.5",
  // a calendar with a tick
  cancel: "M5 6h14v13H5zM5 10h14M9 4v4M15 4v4M9.5 14.5l1.8 1.8 3.4-3.6",
  // a cup
  breakfast: "M5 9h11v5a4 4 0 0 1-4 4H9a4 4 0 0 1-4-4zM16 10.5h1.5a2 2 0 0 1 0 4H16M8 4.5v2M11 4.5v2",
  // wifi arcs
  wifi: "M4 9.5a12 12 0 0 1 16 0M7 12.8a7.5 7.5 0 0 1 10 0M10 16a3 3 0 0 1 4 0M12 19h.01",
  // a P sign
  parking: "M6 4h12v16H6zM10 16V8h3a2.5 2.5 0 0 1 0 5h-3",
  // a small house with a heart
  small: "M4 11l8-6.5 8 6.5M6 9.5V19h12V9.5M12 16.5s-2.6-1.6-2.6-3.2a1.4 1.4 0 0 1 2.6-.7 1.4 1.4 0 0 1 2.6.7c0 1.6-2.6 3.2-2.6 3.2z",
};

export default function FeatureIcon({ name }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"
         strokeLinejoin="round" aria-hidden="true">
      <path d={PATHS[name] || PATHS.small} />
    </svg>
  );
}
