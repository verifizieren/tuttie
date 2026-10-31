import test from "node:test";
import assert from "node:assert/strict";
import TuttieFace from "./face.js";

test("an instant initial sleep stays finite when the first frame shares its timestamp", () => {
  // Exercise the animation math without a browser or a drawing surface.
  const face = Object.create(TuttieFace.prototype);
  Object.assign(face, {
    current: Array(43).fill(0), gaze: [0, 0], speaking: 0, hearing: 0,
    voiceTarget: [0, 0], draw() {},
  });
  const previous = globalThis.requestAnimationFrame;
  globalThis.requestAnimationFrame = () => 1;
  try {
    face.sleep(0);
    face.frame(face.start);
    assert.ok(face.current.every(Number.isFinite));
    assert.deepEqual(face.current, face.to);
    face.wake();
    face.frame(face.start + 100);
    assert.ok(face.current.every(Number.isFinite));
  } finally {
    if (previous === undefined) delete globalThis.requestAnimationFrame;
    else globalThis.requestAnimationFrame = previous;
  }
});
