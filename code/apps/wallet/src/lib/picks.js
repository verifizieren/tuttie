// What the wallet asks Tuttie after the user swiped through the hotel cards: book the best
// liked deal (the lowest agreed price), and name the other liked hotels with their prices, so
// that if the user declines the booking on the approval sheet, Tuttie can offer the next one.

const priceOf = card => card.agreed_chf ?? card.price_chf ?? Infinity;  // no price: last

/** The liked cards, best deal first. */
export const byPrice = liked => [...liked].sort((a, b) => priceOf(a) - priceOf(b));

/** { best, text, shown }: `text` goes to Tuttie, `shown` is what the history keeps. */
export function bookingRequest(liked) {
  const [best, ...others] = byPrice(liked);
  let text = `Book ${best.name} (${best.node_id})${best.agreed_chf != null ? " at the agreed price" : ""}.`;
  if (others.length) {
    text += ` If I decline it, I also liked: ${others.map(c => `${c.name} (${c.node_id})${Number.isFinite(priceOf(c)) ? ` at CHF ${priceOf(c)}` : ""}`).join(", ")}.`;
  }
  return { best, text, shown: `Book ${best.name}` };
}
