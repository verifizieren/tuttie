// Tests for the wallet's sounds (lib/sounds.js) with a recording fake of Web Audio. `npm test`.
import assert from "node:assert/strict";
import { test } from "node:test";
import { CHIME, playAccepted, scheduleChime, unlockSound } from "./sounds.js";

function fakeContext(state = "running") {
  const log = [];
  const param = name => ({
    setValueAtTime: (v, t) => log.push([name, "set", +v.toFixed(4), +t.toFixed(3)]),
    exponentialRampToValueAtTime: (v, t) => log.push([name, "ramp", +v.toFixed(4), +t.toFixed(3)]),
  });
  return {
    log, state, currentTime: 10, destination: { name: "speakers" },
    resume() { this.state = "running"; log.push(["resume"]); return Promise.resolve(); },
    createOscillator: () => ({
      type: null, frequency: param("freq"),
      connect(gain) { log.push(["connect"]); return gain; },
      start: t => log.push(["start", +t.toFixed(3)]), stop: t => log.push(["stop", +t.toFixed(3)]),
    }),
    createGain: () => ({ gain: param("gain"), connect: dest => { log.push(["to", dest.name]); return dest; } }),
  };
}

test("the chime is two rising notes, each with a soft octave, that fade out", () => {
  const ctx = fakeContext();
  assert.equal(scheduleChime(ctx), 2);
  const freqs = ctx.log.filter(e => e[0] === "freq").map(e => e[2]);
  assert.deepEqual(freqs, [1318.5, 2637, 1760, 3520]);
  const starts = ctx.log.filter(e => e[0] === "start").map(e => e[1]);
  assert.deepEqual(starts, [10.01, 10.01, 10.095, 10.095]);  // the second note a little later
  const peaks = ctx.log.filter(e => e[0] === "gain" && e[1] === "ramp" && e[2] > 0.001).map(e => e[2]);
  assert.ok(peaks.every(p => p <= 0.22), "never louder than the volume");
  const lastStop = Math.max(...ctx.log.filter(e => e[0] === "stop").map(e => e[1]));
  assert.ok(lastStop - 10 < 0.8, "short: under 0.8 s");
  assert.equal(ctx.log.filter(e => e[0] === "to" && e[1] === "speakers").length, 4);
  assert.ok(CHIME[1].freq > CHIME[0].freq);
});

test("without Web Audio (old browsers, Node) nothing breaks", () => {
  assert.equal(globalThis.AudioContext, undefined);
  unlockSound();
  playAccepted();
});

test("with Web Audio: the tap unlocks it, the approval plays it and the phone buzzes", () => {
  const made = [];
  const buzzes = [];
  globalThis.AudioContext = function AudioContext() { const ctx = fakeContext("suspended"); made.push(ctx); return ctx; };
  const realNavigator = Object.getOwnPropertyDescriptor(globalThis, "navigator");
  Object.defineProperty(globalThis, "navigator", { value: { vibrate: p => buzzes.push(p) }, configurable: true });
  try {
    unlockSound();
    playAccepted();
    assert.equal(made.length, 1, "one shared audio context");
    assert.deepEqual(made[0].log[0], ["resume"]);
    assert.equal(made[0].log.filter(e => e[0] === "start").length, 4);
    assert.deepEqual(buzzes, [[18, 60, 28]]);
  } finally {
    delete globalThis.AudioContext;
    if (realNavigator) Object.defineProperty(globalThis, "navigator", realNavigator);
  }
});
