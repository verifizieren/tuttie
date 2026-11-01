// The deck: a step machine over beats.js, the shared eyes, the phone with the live wallet, and
// the presenter channel. Keys: → Space PageDown next · ← PageUp back · Home End · B (or .) black
// · F fullscreen · N presenter view · V fallback recording · L live/fallback · R reset.

import { activeBeats, flatten } from "./beats.js";
import { createFace, eyeStyle, OPEN, WALLET_OPEN } from "./eyes.js";

const params = new URLSearchParams(location.search);
const beats = activeBeats(location.search);
const flat = flatten(beats);

const stage = document.getElementById("stage");
const sections = Object.fromEntries([...document.querySelectorAll(".beat")].map(el => [el.dataset.beat, el]));
const phone = document.getElementById("phone");
const wallet = document.getElementById("wallet");
const video = document.getElementById("fallback");
const blackout = document.getElementById("black");
const faceBox = document.getElementById("face");

// Beats switched off in beats.js never show.
for (const [id, el] of Object.entries(sections)) if (!beats.some(b => b.id === id)) el.remove();

// ---------- stage: 1920x1080 scaled into the window ----------

function fit() {
  const scale = Math.min(innerWidth / 1920, innerHeight / 1080);
  const x = (innerWidth - 1920 * scale) / 2, y = (innerHeight - 1080 * scale) / 2;
  stage.style.transform = `translate(${x}px, ${y}px) scale(${scale})`;
}
addEventListener("resize", fit);
fit();

// ---------- the phone and the live wallet ----------

/** Where the phone sits on stage (unscaled frame 414x868, 12 px around the 390x844 screen). */
const PHONE = { x: 360, y: 54, scale: 1.12, frame: 12 };
phone.style.left = `${PHONE.x}px`;
phone.style.top = `${PHONE.y}px`;
phone.style.transform = `scale(${PHONE.scale})`;

/** A URL from the query string, accepted only on this origin (no javascript:, no other sites):
 *  the framed pages share the wallet's cookie, so a foreign or script URL would be an XSS hole. */
export function sameOrigin(value, fallback) {
  if (!value) return fallback;
  try {
    const url = new URL(value, location.href);
    return url.origin === location.origin ? url.href : fallback;
  } catch {
    return fallback;
  }
}

// The deck lives next to the wallet (/presentation/ and /wallet/); ?wallet= may point to another
// path on the same origin, for layout checks.
wallet.src = sameOrigin(params.get("wallet"), "/wallet/");
const owner = document.getElementById("owner");   // gone when the owner beat is switched off
if (owner) {
  owner.src = sameOrigin(params.get("ownerview"), "/owner/");
  owner.addEventListener("load", () => { forwardKeys(owner); keepFocus(); });
}

/** Give the wallet the insets of a home-screen app on an iPhone, so the status bar is clear. */
function walletInsets() {
  try {
    const doc = wallet.contentDocument;
    if (!doc || doc.getElementById("deck-insets")) return;
    const style = doc.createElement("style");
    style.id = "deck-insets";
    style.textContent = ".app { --top: 59px; } .app:not(.typing) { --bottom: 34px; }";
    doc.head.append(style);
  } catch { /* another origin (?wallet=): leave it as it is */ }
}
wallet.addEventListener("load", () => { walletInsets(); forwardKeys(wallet); keepFocus(); });

/** The Tuttie card's face canvas inside the wallet, or null (not loaded, another origin). */
function walletCanvas() {
  try { return wallet.contentDocument?.querySelector(".card.agent canvas") || null; } catch { return null; }
}

/** Hide (or show again) the wallet's own eyes while the deck's eyes fly in, so only one pair of
 *  eyes is ever on screen. A style in the wallet's document: the wallet's code is untouched. */
function hideWalletEyes(hidden) {
  try {
    const doc = wallet.contentDocument;
    if (!doc) return;
    if (!doc.getElementById("deck-handoff")) {
      const style = doc.createElement("style");
      style.id = "deck-handoff";
      // At once both ways: no ghost of the closed card while hiding, and on landing the wallet's
      // eyes are fully there under the deck's fading ones (two half-faded pairs would dim).
      style.textContent = "html.deck-handoff .card.agent canvas { opacity: 0 !important; }";
      doc.head.append(style);
    }
    doc.documentElement.classList.toggle("deck-handoff", hidden);
  } catch { /* another origin: nothing to hide */ }
}

// ---------- demo driver (demo.js, optional) ----------

let demo = null;
const ran = new Set();
const pending = new Set();      // demo steps still waiting on the wallet (shown in the presenter view only)
try {
  const { createDemo } = await import("./demo.js");
  demo = createDemo(wallet);
} catch (e) {
  console.warn("[deck] demo.js is not available; demo steps do nothing.", e);
}
const demoStep = id => demo?.steps?.find(step => step.id === id);

let runGeneration = 0;           // bumped by reset(): an older step's finish must not touch the new run
function runDemo(id) {
  if (passive) return console.warn("[deck] another deck tab drives the wallet; this one only shows");
  if (!id || ran.has(id)) return;
  const mine = runGeneration;
  ran.add(id);
  const step = demoStep(id);
  if (!step) return console.warn(`[deck] no demo step "${id}"`);
  pending.add(id);
  broadcast();
  Promise.resolve().then(() => step.run())
    .catch(e => console.warn(`[deck] demo step "${id}" failed`, e))
    .finally(() => { if (mine === runGeneration) { pending.delete(id); broadcast(); } });
}

// ---------- fallback recording ----------

// Loaded on the first V or L, so a missing file costs nothing until it is needed.
let fallbackLoad = null;
function loadFallback() {
  fallbackLoad ??= new Promise(resolve => {
    video.addEventListener("loadeddata", () => resolve(true), { once: true });
    video.addEventListener("error", () => resolve(false), { once: true });
    try {
      if (typeof demo?.fallback === "function") demo.fallback(video);
      else {
        const src = typeof demo?.fallback === "string" ? demo.fallback : "media/fallback.webm";
        // Safari versions without VP9 get the H.264 copy next to it.
        video.src = video.canPlayType('video/webm; codecs="vp9"') ? src : src.replace(/\.webm$/, ".mp4");
      }
    } catch (e) {
      console.warn("[deck] fallback setup failed", e);
    }
    if (!video.getAttribute("src") && !video.querySelector("source")) video.src = "media/fallback.webm";
    video.load();
    setTimeout(() => resolve(video.readyState >= 2), 4000);
  });
  return fallbackLoad;
}

async function showFallback(on, restart = false) {
  if (on && !(await loadFallback())) {
    fallbackLoad = null;  // try again next time (the file may be added during rehearsal)
    return console.warn("[deck] no fallback recording (media/fallback.webm)");
  }
  phone.classList.toggle("fallback", on);
  if (on) {
    if (restart) video.currentTime = 0;
    video.play().catch(() => {});
  } else {
    video.pause();
  }
  broadcast();
}

// ---------- eyes ----------

const bigFace = createFace(faceBox);
/** Tuttie's eyes, large and centred (beat 3). */
const FACE_HOME = { x: 440, y: 248, w: 1040, h: 520 };
const MOVE_MS = 1500;           // the eyes' flight into the phone
const SETTLE_MS = 900;          // at most this long on the wallet's eyes, waiting for them to be fully open
const FADE_MS = 350;            // the deck's eyes fade off the wallet's own (deck.css #face.gone)
const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");

/** The faint halo around the wallet's eyes (lib/face.js shadow), sized to an eye of `w` px. */
const halo = w => `0 0 ${Math.max(2, w * 0.12).toFixed(1)}px rgba(217, 119, 87, .35)`;

function placeFace(rect, pose) {
  Object.assign(faceBox.style, { left: `${rect.x}px`, top: `${rect.y}px`, width: `${rect.w}px`, height: `${rect.h}px` });
  bigFace.eyes.forEach((eye, i) => Object.assign(eye.style, eyeStyle(pose, i ? "right" : "left"),
                                                 { boxShadow: halo(rect.w * pose.w / 100) }));
}

/** The two eyes of a pose in a rect, as stage px rects [left, right]. */
function eyeRects(rect, pose) {
  return ["left", "right"].map(side => {
    const [cx, cy] = pose[side];
    const w = rect.w * pose.w / 100, h = rect.h * pose.h / 100;
    return { x: rect.x + rect.w * cx / 100 - w / 2, y: rect.y + rect.h * cy / 100 - h / 2, w, h };
  });
}

/** Wallet CSS px → stage px (the phone is scaled and sits at PHONE on the stage). */
function toStage(r) {
  const s = PHONE.scale;
  return { x: PHONE.x + (PHONE.frame + r.x) * s, y: PHONE.y + (PHONE.frame + r.y) * s, w: r.w * s, h: r.h * s };
}

// The wallet's eyes are read off its canvas (a small copy, so reading is cheap), so the deck's
// eyes land on what the wallet really draws: its gaze, its expression, a blink.
const sample = Object.assign(document.createElement("canvas"), { width: 256, height: 128 });
const sampleCtx = sample.getContext("2d", { willReadFrequently: true });

/** Where the wallet draws its eyes now, in stage px: { eyes: [left, right], open } where `open`
 *  says they are fully open (not asleep, not mid-blink, not the glad half-closed waking look).
 *  Null when the canvas is not there. If the read eyes are not fully open, the open pose of
 *  the wallet's face (eyes.js WALLET_OPEN) in the canvas is returned instead. */
function walletEyes() {
  const canvas = walletCanvas();
  const r = canvas?.getBoundingClientRect();
  if (!r || r.width < 1) return null;
  const box = toStage({ x: r.left, y: r.top, w: r.width, h: r.height });
  let found = null;
  try {
    sampleCtx.clearRect(0, 0, 256, 128);
    sampleCtx.drawImage(canvas, 0, 0, 256, 128);
    const data = sampleCtx.getImageData(0, 0, 256, 128).data;
    found = [[0, 128], [128, 256]].map(([x0, x1]) => {
      let left = 1e9, top = 1e9, right = -1, bottom = -1;
      for (let y = 0; y < 128; y++) {
        for (let x = x0; x < x1; x++) {
          if (data[(y * 256 + x) * 4 + 3] < 160) continue;  // the eye itself, not its halo
          if (x < left) left = x; if (x > right) right = x;
          if (y < top) top = y; if (y > bottom) bottom = y;
        }
      }
      if (right < 0) return null;
      return { x: box.x + box.w * left / 256, y: box.y + box.h * top / 128,
               w: box.w * (right - left + 1) / 256, h: box.h * (bottom - top + 1) / 128 };
    });
  } catch { /* a tainted or lost canvas: use the open pose */ }
  const open = Boolean(found?.[0] && found[1] && found.every(e => e.h > box.h * 0.45));
  return { eyes: open ? found : eyeRects(box, WALLET_OPEN), open };
}

let faceMove = 0;               // the running frame of faceIntoPhone, cancelled by faceHome
let moveGeneration = 0;
function faceHome(shown) {
  cancelAnimationFrame(faceMove);
  moveGeneration++;
  faceBox.classList.remove("gone");
  placeFace(FACE_HOME, OPEN);
  faceBox.classList.toggle("shown", shown);
  hideWalletEyes(false);
}

const ease = t => (t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
const mix = (a, b, t) => ({ x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t, w: a.w + (b.w - a.w) * t, h: a.h + (b.h - a.h) * t });

/** Magic move: while the wallet opens its Tuttie card (demo step "open"), the big eyes shrink
 *  into the phone and land on the open card's awake eyes, then hand over to them, so it reads
 *  as one pair of eyes. The wallet's own eyes stay hidden until then. Each frame aims at where
 *  the wallet draws its eyes now; on arrival the deck's eyes follow them until they are fully
 *  open (at most SETTLE_MS), the wallet's eyes appear under them and the deck's fade away. */
function faceIntoPhone() {
  cancelAnimationFrame(faceMove);
  const mine = ++moveGeneration;
  hideWalletEyes(true);
  const from = eyeRects(FACE_HOME, OPEN);
  // The face box becomes the whole stage, so each eye is placed in stage px (as % of 1920x1080).
  Object.assign(faceBox.style, { left: "0px", top: "0px", width: "1920px", height: "1080px" });
  const put = rects => bigFace.eyes.forEach((eye, i) => {
    const e = rects[i];
    Object.assign(eye.style, {
      left: `${e.x / 19.2}%`, top: `${e.y / 10.8}%`, width: `${e.w / 19.2}%`, height: `${e.h / 10.8}%`,
      borderRadius: OPEN.radius, boxShadow: halo(e.w),
    });
  });
  put(from);
  const start = performance.now();
  const moveMs = reducedMotion.matches ? 1 : MOVE_MS;
  let landed = 0, fading = 0;
  const frame = now => {
    if (mine !== moveGeneration) return;
    const target = walletEyes();
    const t = Math.min(1, (now - start) / moveMs);
    if (target) put(from.map((e, i) => mix(e, target.eyes[i], ease(t))));
    if (t >= 1 && !landed) landed = now;
    // Arrived: wait (briefly) for the wallet's eyes to be fully open, then crossfade.
    if (landed && !fading && (target?.open || now - landed > SETTLE_MS || !target)) {
      fading = now;
      hideWalletEyes(false);
      faceBox.classList.add("gone");
    }
    if (fading && now - fading > FADE_MS + 50) {
      faceBox.classList.remove("shown");
      return;
    }
    faceMove = requestAnimationFrame(frame);
  };
  faceMove = requestAnimationFrame(frame);
}

// ---------- the step machine ----------

let pos = 0;
let startedAt = 0;              // ms timestamp of entering beat 1 (the timer)
const entered = {};             // beat id → seconds since start when first entered
const isOn = (at, index, beat) => {
  const resolve = v => {
    if (v === undefined) return undefined;
    if (/^\d+$/.test(v)) return Number(v);
    const i = beat.steps.findIndex(step => step.demo === v);
    return i < 0 ? Infinity : i;
  };
  const from = resolve(at.dataset.at) ?? 0;
  const until = resolve(at.dataset.until) ?? Infinity;
  return index >= from && index < until;
};

function render(previous, forward) {
  const { beat, index } = flat[pos];
  const prevBeat = previous ? flat[previous.pos].beat : null;
  for (const [id, el] of Object.entries(sections)) {
    const active = id === beat.id;
    el.classList.toggle("active", active);
    if (!active) continue;
    el.classList.toggle("magic", id === "demo" && prevBeat?.id === "tuttie" && forward);
    for (let i = 0; i < 4; i++) el.classList.toggle(`step-${i}`, i === index);
    for (const item of el.querySelectorAll(".s")) item.classList.toggle("on", isOn(item, index, beat));
  }
  // The eyes: centred in beat 3, moving into the phone (onto the opening wallet card) on the way
  // to beat 4, hidden otherwise.
  if (beat.id === "tuttie") faceHome(true);
  else if (beat.id === "demo" && prevBeat?.id === "tuttie" && forward) faceIntoPhone();
  else if (prevBeat?.id !== beat.id) { faceBox.classList.remove("shown"); }
}

function go(target, { step = false } = {}) {
  target = Math.max(0, Math.min(flat.length - 1, target));
  if (target === pos && step) return;
  const previous = { pos };
  const forward = target > pos;
  pos = target;
  const { beat, step: s } = flat[pos];
  if (!startedAt && forward && pos > 0) startedAt = Date.now();
  if (startedAt && !(beat.id in entered)) entered[beat.id] = (Date.now() - startedAt) / 1000;
  render(previous, forward);
  keepFocus();
  // Only a single click forward drives the wallet. Entering the demo beat opens the Tuttie card
  // (demo step "open"), so the eyes moving in land on its awake eyes.
  if (step && forward && beat.id === "demo" && flat[pos].index === 0) runDemo("open");
  if (step && forward && s.demo) runDemo(s.demo);
  if (phone.classList.contains("fallback")) {
    if (beat.id !== "demo") video.pause();
    else video.play().catch(() => {});  // back in the demo beat: the recording goes on
  }
  broadcast();
}

async function reset() {
  runGeneration++;
  ran.clear();
  pending.clear();
  startedAt = 0;
  for (const k of Object.keys(entered)) delete entered[k];
  blackout.classList.remove("on");
  showFallback(false);
  go(0);
  faceHome(false);
  try { await demo?.reset?.(); } catch (e) { console.warn("[deck] demo reset failed", e); }
}

// ---------- keys ----------

const STEP_KEYS = new Set(["ArrowRight", " ", "PageDown", "ArrowDown", "ArrowLeft", "PageUp", "ArrowUp"]);
const DEBOUNCE_MS = 300;        // a clicker that fires twice, or a held key, moves one step only
let lastStep = 0;
function key(e) {
  if (e.metaKey || e.ctrlKey || e.altKey) return false;
  const k = e.key;
  if (e.repeat) return true;    // a held key: swallow it
  if (STEP_KEYS.has(k)) {
    const now = performance.now();
    if (now - lastStep < DEBOUNCE_MS) return true;
    lastStep = now;
  }
  if (k === "ArrowRight" || k === " " || k === "PageDown" || k === "ArrowDown") go(pos + 1, { step: true });
  else if (k === "ArrowLeft" || k === "PageUp" || k === "ArrowUp") go(pos - 1, { step: true });
  else if (k === "Home") go(0);
  else if (k === "End") go(flat.length - 1);
  else if (k === "b" || k === "B" || k === ".") { blackout.classList.toggle("on"); broadcast(); }
  else if (k === "f" || k === "F") toggleFullscreen();
  else if (k === "n" || k === "N") openPresenter();
  else if (k === "v" || k === "V") showFallback(!phone.classList.contains("fallback"), true);
  else if (k === "l" || k === "L") showFallback(!phone.classList.contains("fallback"));
  else if (k === "r" || k === "R") reset();
  else return false;
  return true;
}
addEventListener("keydown", e => { claim(); if (key(e)) e.preventDefault(); });

/** Keys pressed while a framed page has focus still drive the deck, unless someone is typing
 *  in it (the owner token, a request typed by hand). */
function forwardKeys(frame) {
  try {
    frame.contentWindow.addEventListener("keydown", e => {
      if (e.target.closest?.("input, textarea, [contenteditable]")) return;
      claim();
      if (key(e)) e.preventDefault();
    });
    frame.contentWindow.addEventListener("pointerdown", e => { if (e.isTrusted) lastFrameTouch = Date.now(); }, true);
  } catch { /* other origin */ }
}

// A framed page that focuses itself (autofocus, late React mount) gives the focus back, unless a
// person just clicked into it (to type in the wallet by hand).
let lastFrameTouch = 0;
addEventListener("blur", () => setTimeout(() => { if (Date.now() - lastFrameTouch > 1000) keepFocus(); }, 0));

/** A framed page that focuses itself (autofocus) must not take the clicker away from the deck. */
function keepFocus() {
  if (document.activeElement?.tagName === "IFRAME") stage.focus({ preventScroll: true });
}

function toggleFullscreen() {
  if (document.fullscreenElement) document.exitFullscreen();
  else document.documentElement.requestFullscreen?.().catch(() => {});
}

// Hide the pointer when it rests.
let idle = 0;
addEventListener("pointermove", () => {
  document.body.classList.remove("idle");
  clearTimeout(idle);
  idle = setTimeout(() => document.body.classList.add("idle"), 1500);
});

// ---------- presenter view ----------

const channel = "BroadcastChannel" in window ? new BroadcastChannel("tuttie-deck") : null;

function openPresenter() {
  window.open(`presenter.html${location.search}`, "tuttie-presenter", "width=1280,height=800");
}

function broadcast() {
  if (passive) return;
  channel?.postMessage({
    type: "state", pos, startedAt, entered: { ...entered },
    black: blackout.classList.contains("on"), fallback: phone.classList.contains("fallback"),
    pending: [...pending],
    beats: beats.map(b => b.id),
  });
}

// Tabs of one browser share the wallet's session, so only one deck may drive it: the tab used
// last claims the stage, every other deck tab turns passive (no presenter keys, no demo steps).
const deckId = Math.random().toString(36).slice(2);
let passive = false;
function claim() {
  if (!passive && claimed) return;
  passive = false;
  claimed = true;
  document.documentElement.classList.remove("passive");
  channel?.postMessage({ type: "claim", id: deckId });
  broadcast();
}
let claimed = false;

channel?.addEventListener("message", ({ data }) => {
  if (data?.type === "claim" && data.id !== deckId) {
    passive = true;
    document.documentElement.classList.add("passive");
  }
  if (passive) return;
  if (data?.type === "hello") broadcast();
  if (data?.type === "key") key({ key: data.key });
});

// Start: black, eyes waiting at home. ?step=n opens a given step (for rehearsal and screenshots).
faceHome(false);
claim();
go(Number(params.get("step")) || 0);
window.deck = { go: n => go(n), next: () => go(pos + 1, { step: true }), get pos() { return pos; }, steps: flat.length };
