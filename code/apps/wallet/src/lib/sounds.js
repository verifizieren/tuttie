// The wallet's sounds, made in the browser (Web Audio): no audio files, nothing to license.
//
// accepted: a short, bright two-note chime when a payment was approved and recorded (the
// checkmark after Face ID), plus a short vibration where the phone supports it (Android).
//
// Phones only play sound that a tap unlocked: call unlockSound() inside the tap's handler (e.g.
// the Approve button), before anything is awaited; the chime may then play seconds later.
// Without Web Audio (old browsers, tests) every function quietly does nothing.

let context = null;

/** The shared audio context, made on first use (null where the browser has no Web Audio). */
function audio() {
  if (context) return context;
  const AudioContext = globalThis.AudioContext || globalThis.webkitAudioContext;
  context = AudioContext ? new AudioContext() : null;
  return context;
}

/** Call from a tap: lets later sounds play on phones (iOS starts audio only from a gesture). */
export function unlockSound() {
  const ctx = audio();
  if (ctx && ctx.state !== "running") ctx.resume().catch(() => {});
}

// Two quick rising notes (E6, then A6 a little later and longer), each a sine with a soft
// octave above, a 5 ms attack and an exponential fade: bright, short, never shrill.
export const CHIME = [
  { freq: 1318.5, at: 0, length: 0.32 },
  { freq: 1760.0, at: 0.085, length: 0.55 },
];
const VOLUME = 0.22;

/**
 * Schedule the accepted chime on `ctx` from `ctx.currentTime` (separate from playing, so tests
 * can pass a recording fake). Returns the number of notes scheduled.
 */
export function scheduleChime(ctx, notes = CHIME, volume = VOLUME) {
  const start = ctx.currentTime + 0.01;
  for (const { freq, at, length } of notes) {
    for (const [ratio, level] of [[1, 1], [2, 0.18]]) {  // the note and a soft octave for shine
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sine";
      osc.frequency.setValueAtTime(freq * ratio, start + at);
      gain.gain.setValueAtTime(0.0001, start + at);
      gain.gain.exponentialRampToValueAtTime(volume * level, start + at + 0.005);
      gain.gain.exponentialRampToValueAtTime(0.0001, start + at + length);
      osc.connect(gain).connect(ctx.destination);
      osc.start(start + at);
      osc.stop(start + at + length + 0.02);
    }
  }
  return notes.length;
}

/** The payment went through: the chime, and a short double buzz where phones vibrate. */
export function playAccepted() {
  try {
    const ctx = audio();
    if (ctx) {
      if (ctx.state !== "running") ctx.resume().catch(() => {});
      scheduleChime(ctx);
    }
    globalThis.navigator?.vibrate?.([18, 60, 28]);
  } catch {
    // A sound is never worth breaking the payment flow for.
  }
}
