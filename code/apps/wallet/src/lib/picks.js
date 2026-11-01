// What the wallet asks Tuttie after the user swiped through the hotel cards: book the best
// liked deal (the lowest agreed price), and name the other liked hotels (cheapest first, without
// prices: a card's price is not what booking that hotel costs; its approval sheet shows the total),
// so that if the user declines the booking on the approval sheet, Tuttie can offer the next one.

// Hotel names come from the registry and the hotels' own cards, yet this text reaches Tuttie as
// the user's words: a name is cut to one short line without brackets or quotes, and a node id
// keeps only the characters node ids have, so a hostile name cannot pose as an instruction.
const NAME_MAX = 60;
const clean = value => (typeof value === "string" ? value : "").replace(/[()[\]{}<>"`\\]/g, " ")
  .replace(/\s+/g, " ").trim().slice(0, NAME_MAX).trim();
const nodeId = value => (typeof value === "string" ? value : "").replace(/[^\w.-]/g, "").slice(0, 80);
const label = card => `${clean(card.name) || "this hotel"} (${nodeId(card.node_id)})`;

const priceOf = card => card.agreed_chf ?? card.price_chf ?? Infinity;  // no price: last

/** The liked cards, best deal first. */
export const byPrice = liked => [...liked].sort((a, b) => priceOf(a) - priceOf(b));

/** { best, text, shown }: `text` goes to Tuttie, `shown` is what the history keeps. */
export function bookingRequest(liked) {
  const [best, ...others] = byPrice(liked);
  let text = `Book ${label(best)}${best.agreed_chf != null ? " at the agreed price" : ""}.`;
  if (others.length) {
    text += ` If I decline it, I also liked: ${others.map(label).join(", ")}.`;
  }
  return { best, text, shown: `Book ${best.name}` };
}
