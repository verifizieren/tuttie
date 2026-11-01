// Tuttie's eyes for the deck: the wallet's own face (face.js, a copy of apps/wallet/src/lib/face.js),
// drawn on a canvas in its 2:1 box. Black glossy eyes with a square catchlight, natural blinks and
// gentle idle glances, exactly as on the wallet's Tuttie card, only bigger.

import TuttieFace from "./face.js";

/** Start the wallet's face on `canvas`, awake and calm (the card's resting look). */
export function createFace(canvas) {
  const face = new TuttieFace(canvas);
  face.wake("neutral", 0);
  return face;
}
