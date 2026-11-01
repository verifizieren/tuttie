// Directs Tuttie's eyes from its presence (lib/presence.js): the one place that decides how the
// face looks for what Tuttie is doing. It only uses the face's public methods (set, lookAt,
// setVoice, sleep, wake; see lib/face.js), so any face with those methods can be directed.
// A face that wants to animate the presence itself defines onPresence(event); then the director
// steps aside and only forwards (usePresence calls onPresence for every event anyway).
//
//   state  → a base expression plus a loop of looks, so the eyes are never frozen:
//            searching scans left and right, thinking looks up and around, listening nods,
//            waiting looks down at the approval sheet, watching follows the dragged card;
//            typing closes the eyes; a closed card (asleep) rests awake and neutral
//   levels → setVoice: the eyes pulse with Tuttie's voice and open up while the user talks
//   cue    → a short reaction (a glad blink at an agreement, a suspicious squint at a blocked
//            scam), after which the state's loop goes on
import { LISTENING, MOOD, THINKING, WATCHING } from "./activity.js";

export const LOOK_MS = 1600;  // how long each look of a loop lasts
export const MOOD_MS = 3500;  // how long an answer's mood shows before Tuttie listens again
export const WAKE_MS = 1300;  // how long the glad waking face holds before the state's looks start

// Glances while Tuttie searches the agent web: side to side, like reading a list.
const SEARCHING = [
  { name: "amazement", look: [-.7, -.1] }, { name: "neutral", look: [-.2, -.15] },
  { name: "amazement", look: [.4, -.1] }, { name: "neutral", look: [.75, -.2] },
];
// Bargaining: a careful, sceptical look at the hotel's number, now and then a glance aside.
const NEGOTIATING = [
  { name: "suspicion", look: [0, 0] }, { name: "skepticism", look: [.35, -.15] },
  { name: "suspicion", look: [-.2, .05] }, { name: "skepticism", look: [0, -.3] },
];
// While Tuttie talks it looks at the user, with small natural glances.
const SPEAKING = [
  { name: "attentive", look: [0, 0] }, { name: "listening", look: [.12, -.06] },
  { name: "attentive", look: [-.08, .04] },
];
const LOOPS = {
  idle: LISTENING, listening: LISTENING, speaking: SPEAKING, thinking: THINKING, searching: SEARCHING,
  negotiating: NEGOTIATING, booking: THINKING, watching: WATCHING,
};
// A held look for states that do not loop: [expression, x, y].
const HOLD = {
  waiting: ["pleading", 0, .55],   // looking down at the approval sheet
  error: ["sadness", 0, .2],
};
// Short reactions to cues: [expression, ms, optional look]; the loop resumes after `ms`.
export const REACTIONS = {
  wake: ["happiness", 700], tap: ["excitement", 600], new_chat: ["happiness", 700],
  user_said: ["attentive", 500, [0, .25]],            // a small nod: got it
  posted: ["amazement", 700],
  scam_blocked: ["suspicion", 900, [.6, .1]],         // a sideways look at the forged hotel
  offer: ["happiness", 450],
  counter: ["skepticism", 600],
  agreement: ["excitement", 900],
  cards: ["happiness", 600, [0, .5]],
  approval_requested: ["pleading", 600, [0, .55]],
  approved: ["happiness", 900], declined: ["sadness", 1200],
  booked: ["excitement", 1100], paid: ["happiness", 600, [0, .25]],
};

/**
 * @param face    the face instance (or a function returning it, for a React ref)
 * @param timers  { setTimeout, clearTimeout } (tests pass fake ones)
 * @returns onEvent(event): give it every presence event; stop(): clears all timers
 */
export function createFaceDirector(face, timers = globalThis) {
  const get = typeof face === "function" ? face : () => face;
  let state = "asleep", detail = {};
  let loopTimer = null, reactionTimer = null, step = 0;

  const clear = () => {
    timers.clearTimeout(loopTimer);
    timers.clearTimeout(reactionTimer);
    loopTimer = reactionTimer = null;
  };

  /** Show the current state: its hold, or its loop starting after `delay`. */
  function show(delay = 0) {
    const f = get();
    if (!f) return;
    timers.clearTimeout(loopTimer);
    if (state === "typing") return f.sleep();  // the eyes close while the user types
    if (state === "asleep") {  // the card rests in the stack: eyes open, calm, the face's own idle glances
      if (f.asleep) f.wake("neutral");
      return f.set("neutral", 500);
    }
    if (f.asleep) {
      f.wake("happiness");
      delay = Math.max(delay, WAKE_MS);
    }
    if (state === "watching" && detail.lean) return f.lookAt(detail.lean, 0, 120);  // follows the dragged card
    if (HOLD[state]) {
      const [name, x, y] = HOLD[state];
      f.set(name, 500);
      return f.lookAt(x, y, 500);
    }
    if (state === "done") {
      f.set(MOOD[detail.mood] || "happiness", 500);
      f.lookAt(0, 0, 400);
      loopTimer = timers.setTimeout(() => { state = "idle"; show(); }, MOOD_MS);  // then listen again
      return;
    }
    const looks = LOOPS[state] || LISTENING;
    const tick = () => {
      const { name, look } = looks[step++ % looks.length];
      get()?.set(name, 600);
      get()?.lookAt(look[0], look[1], 600);
      loopTimer = timers.setTimeout(tick, LOOK_MS);
    };
    loopTimer = timers.setTimeout(tick, delay);
  }

  function react(name) {
    const reaction = REACTIONS[name];
    const f = get();
    if (!reaction || !f || state === "asleep" || state === "typing") return;
    const [expression, ms, look] = reaction;
    clear();
    f.set(expression, 250);
    if (look) f.lookAt(look[0], look[1], 250);
    reactionTimer = timers.setTimeout(() => { reactionTimer = null; show(); }, ms);
  }

  function onEvent(event) {
    const f = get();
    if (!f || typeof f.onPresence === "function") return;  // the face animates the presence itself
    if (event.type === "levels") return f.setVoice(event.speaking, event.hearing);
    if (event.type === "cue") return react(event.name);
    if (event.type !== "state") return;
    const leanOnly = event.state === "watching" && state === "watching";
    state = event.state;
    detail = event.detail || {};
    if (reactionTimer && !leanOnly) return;  // a reaction is playing; it shows the new state when it ends
    show(leanOnly ? LOOK_MS : 0);
  }

  return { onEvent, stop: clear };
}
