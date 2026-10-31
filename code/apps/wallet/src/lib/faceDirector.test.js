// Tests for the face director (lib/faceDirector.js): presence events → face calls. `npm test`.
import assert from "node:assert/strict";
import { test } from "node:test";
import { createFaceDirector, LOOK_MS, MOOD_MS, REACTIONS, WAKE_MS } from "./faceDirector.js";
import { STATES } from "./presence.js";

/** A face that records its calls, with the same public methods as lib/face.js. */
function fakeFace() {
  const calls = [];
  return {
    calls, asleep: true,
    set: (name) => calls.push(`set:${name}`),
    lookAt: (x, y) => calls.push(`look:${x},${y}`),
    setVoice: (s, h) => calls.push(`voice:${s},${h}`),
    sleep() { this.asleep = true; calls.push("sleep"); },
    wake(name) { this.asleep = false; calls.push(`wake:${name}`); },
  };
}

/** Timers you advance by hand. */
function fakeTimers() {
  let now = 0, id = 0;
  const pending = new Map();
  return {
    setTimeout: (fn, ms) => { pending.set(++id, { at: now + ms, fn }); return id; },
    clearTimeout: t => pending.delete(t),
    advance(ms) {
      const end = now + ms;
      for (;;) {
        const next = [...pending.entries()].sort((a, b) => a[1].at - b[1].at)[0];
        if (!next || next[1].at > end) break;
        pending.delete(next[0]);
        now = next[1].at;
        next[1].fn();
      }
      now = end;
    },
  };
}

function setup() {
  const face = fakeFace(), timers = fakeTimers();
  const director = createFaceDirector(face, timers);
  const state = (s, detail = {}) => director.onEvent({ type: "state", state: s, detail });
  return { face, timers, director, state };
}

test("waking: a glad face first, then the state's looks", () => {
  const { face, timers, state } = setup();
  state("idle");
  assert.deepEqual(face.calls, ["wake:happiness"]);
  timers.advance(WAKE_MS - 1);
  assert.equal(face.calls.length, 1);                 // still holding the waking face
  timers.advance(1);
  assert.deepEqual(face.calls.slice(1), ["set:listening", "look:0,0"]);
  timers.advance(LOOK_MS);
  assert.deepEqual(face.calls.slice(3), ["set:attentive", "look:0.18,-0.08"]);  // the loop goes on
});

test("asleep and typing close the eyes and stop the looks", () => {
  for (const s of ["asleep", "typing"]) {
    const { face, timers, state } = setup();
    face.asleep = false;
    state("searching");
    state(s);
    const count = face.calls.length;
    assert.equal(face.calls.at(-1), "sleep");
    timers.advance(LOOK_MS * 5);
    assert.equal(face.calls.length, count, `${s}: no looks while the eyes are closed`);
  }
});

test("every state moves or holds the eyes; none crashes", () => {
  for (const s of STATES) {
    const { face, timers, state } = setup();
    face.asleep = false;
    state(s, { mood: "happy", lean: 0 });
    timers.advance(LOOK_MS * 3);
    assert.ok(face.calls.length > 0, s);
  }
});

test("searching scans left and right; waiting looks down at the approval sheet", () => {
  const { face, timers, state } = setup();
  face.asleep = false;
  state("searching");
  timers.advance(LOOK_MS * 3);
  const xs = face.calls.filter(c => c.startsWith("look:")).map(c => Number(c.slice(5).split(",")[0]));
  assert.ok(Math.min(...xs) < -0.5 && Math.max(...xs) > 0.3, `scans: ${xs}`);
  state("waiting", { amount: 128 });
  assert.deepEqual(face.calls.slice(-2), ["set:pleading", "look:0,0.55"]);
});

test("an answer shows its mood, then Tuttie listens again", () => {
  const { face, timers, state } = setup();
  face.asleep = false;
  state("done", { mood: "sorry" });
  assert.equal(face.calls[0], "set:guilt");
  timers.advance(MOOD_MS);
  assert.equal(face.calls.at(-2), "set:listening");
});

test("voice levels go straight to the face", () => {
  const { face, director } = setup();
  director.onEvent({ type: "levels", speaking: 0.7, hearing: 0.1 });
  assert.deepEqual(face.calls, ["voice:0.7,0.1"]);
});

test("a cue plays its reaction, then the state's looks resume", () => {
  const { face, timers, state, director } = setup();
  face.asleep = false;
  state("negotiating");
  director.onEvent({ type: "cue", name: "agreement" });
  const [expression, ms] = REACTIONS.agreement;
  assert.equal(face.calls.at(-1), `set:${expression}`);
  timers.advance(ms - 1);
  assert.equal(face.calls.at(-1), `set:${expression}`);  // nothing interrupts the reaction
  timers.advance(1 + LOOK_MS);
  assert.ok(face.calls.slice(-2)[0].startsWith("set:"), "the negotiating loop is back");
});

test("a state change during a reaction waits for the reaction to end", () => {
  const { face, timers, state, director } = setup();
  face.asleep = false;
  state("searching");
  director.onEvent({ type: "cue", name: "scam_blocked" });
  state("waiting", { amount: 128 });
  assert.equal(face.calls.at(-1), "look:0.6,0.1");      // still looking at the blocked hotel
  timers.advance(REACTIONS.scam_blocked[1]);
  assert.deepEqual(face.calls.slice(-2), ["set:pleading", "look:0,0.55"]);
});

test("no reactions while asleep; unknown cues are ignored", () => {
  const { face, director } = setup();
  director.onEvent({ type: "cue", name: "agreement" });
  director.onEvent({ type: "cue", name: "nonsense" });
  assert.deepEqual(face.calls, []);
});

test("the eyes follow a dragged hotel card, then go back to watching", () => {
  const { face, timers, state } = setup();
  face.asleep = false;
  state("watching", { lean: 0 });
  state("watching", { lean: -0.8 });
  assert.equal(face.calls.at(-1), "look:-0.8,0");
  const count = face.calls.length;
  timers.advance(LOOK_MS * 2);
  assert.equal(face.calls.length, count, "no looks while the card is held");
  state("watching", { lean: 0 });
  timers.advance(LOOK_MS);
  assert.ok(face.calls.length > count, "watching looks resume after the drag");
});

test("a face that animates the presence itself is left alone", () => {
  const face = { ...fakeFace(), onPresence() {} };
  const director = createFaceDirector(face, fakeTimers());
  director.onEvent({ type: "state", state: "searching", detail: {} });
  director.onEvent({ type: "levels", speaking: 1, hearing: 0 });
  assert.deepEqual(face.calls, []);
});

test("the face may be missing (a React ref before mount)", () => {
  const director = createFaceDirector(() => null, fakeTimers());
  director.onEvent({ type: "state", state: "idle", detail: {} });
  director.onEvent({ type: "cue", name: "tap" });
  director.stop();
});
