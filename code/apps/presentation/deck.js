// The deck: a step machine over beats.js, the shared eyes, the phone with the live wallet, and
// the presenter channel. Keys: → Space PageDown next · ← PageUp back · Home End · B (or .) black
// · F fullscreen · N presenter view · V fallback recording · L live/fallback · R reset.

import { activeBeats, flatten } from "./beats.js";
import { createFace, eyeStyle, OPEN, ASLEEP } from "./eyes.js";

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

/** The Tuttie card's eye canvas inside the wallet, in wallet CSS px (measured, else typical). */
function cardRect() {
  try {
    const el = wallet.contentDocument.querySelector(".card.agent canvas");
    const r = el?.getBoundingClientRect();
    if (r && r.width > 0) return { x: r.left, y: r.top, w: r.width, h: r.height };
  } catch { /* not same origin */ }
  return { x: 30.3, y: 274.5, w: 329.4, h: 164.7 };
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

function placeFace(rect, pose) {
  Object.assign(faceBox.style, { left: `${rect.x}px`, top: `${rect.y}px`, width: `${rect.w}px`, height: `${rect.h}px` });
  bigFace.eyes.forEach((eye, i) => Object.assign(eye.style, eyeStyle(pose, i ? "right" : "left")));
}

let faceMove = 0;               // the queued frame of faceIntoPhone, cancelled by faceHome
function faceHome(shown) {
  cancelAnimationFrame(faceMove);
  faceBox.classList.remove("moving", "gone");
  placeFace(FACE_HOME, OPEN);
  faceBox.classList.toggle("shown", shown);
}

/** Magic move: the eyes travel into the phone and fall asleep on the wallet's Tuttie card, then
 *  hand over to the real wallet underneath. */
function faceIntoPhone() {
  const r = cardRect();
  const s = PHONE.scale, ox = PHONE.x + PHONE.frame * s, oy = PHONE.y + PHONE.frame * s;
  faceBox.getBoundingClientRect();  // commit the start pose before transitioning
  faceBox.classList.add("moving");
  faceMove = requestAnimationFrame(() => {
    placeFace({ x: ox + r.x * s, y: oy + r.y * s, w: r.w * s, h: r.h * s }, ASLEEP);
    faceBox.classList.add("gone");
  });
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
  // The eyes: centred in beat 3, moving into the phone on the way to beat 4, hidden otherwise.
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
  if (step && forward && s.demo) runDemo(s.demo);   // only a single click forward drives the wallet
  if (beat.id !== "demo" && phone.classList.contains("fallback")) video.pause();
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

const FORWARD = new Set(["ArrowRight", " ", "PageDown", "ArrowDown"]);
const DEBOUNCE_MS = 300;        // a clicker that fires twice, or a held key, moves one step only
let lastForward = 0;
function key(e) {
  if (e.metaKey || e.ctrlKey || e.altKey) return false;
  const k = e.key;
  if (e.repeat) return true;    // a held key: swallow it
  if (FORWARD.has(k)) {
    const now = performance.now();
    if (now - lastForward < DEBOUNCE_MS) return true;
    lastForward = now;
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
addEventListener("keydown", e => { if (key(e)) e.preventDefault(); });

/** Keys pressed while a framed page has focus still drive the deck, unless someone is typing
 *  in it (the owner token, a request typed by hand). */
function forwardKeys(frame) {
  try {
    frame.contentWindow.addEventListener("keydown", e => {
      if (e.target.closest?.("input, textarea, [contenteditable]")) return;
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
  channel?.postMessage({
    type: "state", pos, startedAt, entered: { ...entered },
    black: blackout.classList.contains("on"), fallback: phone.classList.contains("fallback"),
    pending: [...pending],
    beats: beats.map(b => b.id),
  });
}

channel?.addEventListener("message", ({ data }) => {
  if (data?.type === "hello") broadcast();
  if (data?.type === "key") key({ key: data.key });
});

// Start: black, eyes waiting at home. ?step=n opens a given step (for rehearsal and screenshots).
faceHome(false);
go(Number(params.get("step")) || 0);
window.deck = { go: n => go(n), next: () => go(pos + 1, { step: true }), get pos() { return pos; }, steps: flat.length };
